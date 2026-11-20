"""The daily paper-trading run.

run_daily brings one symbol's ledger up to date with a table of daily
prices. It decides what to do from the ledger and the price table alone,
never from the clock or a market calendar:

- Run twice on the same prices, the second run records nothing.
- Run on a holiday or weekend, there is no new price bar, so it records
  nothing.
- Run after one or more missed days, it records every missing day in order,
  with the same result as if it had run on each of them.

It fetches nothing itself. The caller supplies the prices and the
repository, so the run can be tested without a network or a database.
"""

import math
from bisect import bisect_left
from datetime import date

import pandas as pd

from pipeline.ledger import AccountState, apply_day
from pipeline.repository import LedgerEntry, LedgerRepository
from services.backtest import DEFAULT_TRADING_COST_PCT
from services.decisions import make_decision
from services.features import build_features
from services.signal import generate_signal_from_features

DEFAULT_STARTING_EQUITY = 10_000.0


class LedgerGapError(ValueError):
    """The price table does not reach back to the ledger's last recorded day."""


def _bar_dates(price_data: pd.DataFrame) -> list[date]:
    if not isinstance(price_data.index, pd.DatetimeIndex):
        raise ValueError("price_data must be indexed by date.")

    dates = [timestamp.date() for timestamp in price_data.index]

    if any(later <= earlier for earlier, later in zip(dates, dates[1:], strict=False)):
        raise ValueError("price_data must have one row per day, oldest first.")

    return dates


def run_daily(
    symbol: str,
    price_data: pd.DataFrame,
    repository: LedgerRepository,
    *,
    starting_equity: float = DEFAULT_STARTING_EQUITY,
    trading_cost_pct: float = DEFAULT_TRADING_COST_PCT,
) -> list[LedgerEntry]:
    """Record every trading day in `price_data` that the ledger does not have.

    `price_data` is a table of completed daily bars with Open and Close
    columns, indexed by date, oldest first. A bar for a day that is still
    trading must be left out by the caller: once a day is recorded it is
    never recomputed.

    Each new day is accounted the way the backtest does it: the signal from
    the previous bar's close sets the position, the order fills at the day's
    open, and the account is marked at the day's close.

    A symbol with no ledger yet starts on the latest bar, in cash, with
    `starting_equity`. Earlier bars are used only as history for the signal.

    Returns the entries recorded by this call, oldest first. An empty list
    means the ledger was already up to date. Nothing is recorded unless
    every missing day can be accounted.
    """
    cleaned_symbol = symbol.strip().upper()
    if not cleaned_symbol:
        raise ValueError("Symbol is required.")

    if "Open" not in price_data.columns or "Close" not in price_data.columns:
        raise ValueError("Open and Close columns are required for the daily run.")

    if not math.isfinite(starting_equity) or starting_equity <= 0:
        raise ValueError("starting_equity must be a positive, finite amount.")

    # Same cleaning as run_backtest, so both see the same bars.
    clean_prices = price_data.dropna(subset=["Open", "Close"])
    dates = _bar_dates(clean_prices)

    # A day needs the bar before it for the signal and the overnight move.
    if len(dates) < 2:
        return []

    latest = repository.latest(cleaned_symbol)

    if latest is None:
        first = len(dates) - 1
        state = AccountState(equity=starting_equity)
    else:
        if latest.trade_date >= dates[-1]:
            return []

        recorded = bisect_left(dates, latest.trade_date)
        if dates[recorded] != latest.trade_date:
            # Without the last recorded bar there is no telling whether days
            # between it and the table are missing, so refuse to skip them.
            raise LedgerGapError(
                f"The {cleaned_symbol} ledger ends on {latest.trade_date}, which is not "
                f"in the price data (it starts on {dates[0]}). Supply a longer history."
            )

        first = recorded + 1
        state = latest.state

    features = build_features(clean_prices)
    opens = clean_prices["Open"].to_numpy()
    closes = clean_prices["Close"].to_numpy()

    new_entries = []
    for index in range(first, len(dates)):
        # The previous bar's row alone, as in run_backtest. If its features
        # are incomplete (too little history) the signal is a HOLD.
        signal = generate_signal_from_features(
            cleaned_symbol, features.iloc[index - 1 : index]
        )
        target = make_decision(signal["signal"], signal["confidence"], 1.0)["position_pct"]

        prev_close = float(closes[index - 1])
        open_price = float(opens[index])
        close_price = float(closes[index])

        day = apply_day(
            state,
            prev_close=prev_close,
            open_price=open_price,
            close_price=close_price,
            target_pct=target,
            trading_cost_pct=trading_cost_pct,
        )
        new_entries.append(
            LedgerEntry(
                symbol=cleaned_symbol,
                trade_date=dates[index],
                signal_date=dates[index - 1],
                signal=signal["signal"],
                confidence=signal["confidence"],
                reason=signal["reason"],
                prev_close=prev_close,
                open_price=open_price,
                close_price=close_price,
                day=day,
            )
        )
        state = day.state

    # Written only after every day computed, so a bad bar in the middle of a
    # catch-up does not leave the ledger half updated.
    for entry in new_entries:
        repository.append(entry)

    return new_entries
