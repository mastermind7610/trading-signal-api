"""Where the paper-trading ledger is kept.

The daily run reads the account's last recorded day and appends new ones
through the LedgerRepository interface, so the storage behind it can change
without touching the run. InMemoryLedgerRepository is the implementation
used by the tests; it keeps nothing between processes. The one that keeps
the ledger in a database is in pipeline/mongo_repository.py.
"""

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from pipeline.ledger import AccountState, DayResult


@dataclass(frozen=True)
class LedgerEntry:
    """One trading day of one symbol's paper account."""

    symbol: str
    # The day the order filled and the account was marked at the close.
    trade_date: date
    # The previous trading day, whose close produced the signal.
    signal_date: date
    signal: str
    confidence: float
    reason: str
    # The prices the day was accounted with.
    prev_close: float
    open_price: float
    close_price: float
    day: DayResult

    @property
    def state(self) -> AccountState:
        """The account to carry into the next trading day."""
        return self.day.state


class OutOfOrderEntryError(ValueError):
    """An entry is not later than the last one recorded for its symbol."""


class LedgerStorageError(Exception):
    """The storage behind a repository could not be read or written.

    Raised by repositories that keep the ledger somewhere that can fail, so
    callers can handle an outage without knowing which database is in use.
    """


class LedgerRepository(Protocol):
    """Append-only storage for ledger entries, one history per symbol.

    Each symbol's entries are in strictly increasing trade_date order, so a
    symbol has at most one entry per day. Any method may raise
    LedgerStorageError if the storage cannot be reached.
    """

    def latest(self, symbol: str) -> LedgerEntry | None:
        """The most recent entry for the symbol, or None if it has none."""
        ...

    def history(self, symbol: str) -> list[LedgerEntry]:
        """Every entry for the symbol, oldest first."""
        ...

    def append(self, entry: LedgerEntry) -> None:
        """Record an entry.

        Raises OutOfOrderEntryError if its trade_date is not later than the
        symbol's latest entry.
        """
        ...


class InMemoryLedgerRepository:
    """A LedgerRepository held in a dict."""

    def __init__(self) -> None:
        self._entries: dict[str, list[LedgerEntry]] = {}

    def latest(self, symbol: str) -> LedgerEntry | None:
        entries = self._entries.get(symbol)
        return entries[-1] if entries else None

    def history(self, symbol: str) -> list[LedgerEntry]:
        # A copy, so callers cannot change the ledger by editing the list.
        return list(self._entries.get(symbol, []))

    def append(self, entry: LedgerEntry) -> None:
        latest = self.latest(entry.symbol)

        if latest is not None and entry.trade_date <= latest.trade_date:
            raise OutOfOrderEntryError(
                f"{entry.symbol} already has an entry for {latest.trade_date}; "
                f"cannot record {entry.trade_date}."
            )

        self._entries.setdefault(entry.symbol, []).append(entry)
