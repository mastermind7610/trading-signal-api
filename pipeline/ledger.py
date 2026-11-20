"""One day of paper-trading accounting, by the same rules as the backtest.

The backtest replays history in one loop. The daily pipeline has to do the
same sums one day at a time, carrying the account forward between runs, so
the step lives here as a pure function: no I/O, no market data, no signal
logic. tests/test_ledger.py replays whole histories through it and requires
the result to match services.backtest.run_backtest.
"""

import math
from dataclasses import dataclass

from services.backtest import DEFAULT_TRADING_COST_PCT


@dataclass(frozen=True)
class AccountState:
    """A paper account at a day's close."""

    equity: float
    # Fraction of the account held in the stock (0.0 = all cash).
    position_pct: float = 0.0


@dataclass(frozen=True)
class DayResult:
    """What one trading day did to the account."""

    # Fraction of the account in the stock before and after the fill at the open.
    position_before: float
    position_after: float
    # Size of the fill and what it cost, both as fractions of the account.
    traded_pct: float
    traded: bool
    cost_pct: float
    daily_return: float
    # The account at the close.
    equity: float
    position_value: float
    cash: float

    @property
    def state(self) -> AccountState:
        """The account to carry into the next day."""
        return AccountState(equity=self.equity, position_pct=self.position_after)


def _require_positive_price(name: str, value: float) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive, finite price.")


def apply_day(
    state: AccountState,
    *,
    prev_close: float,
    open_price: float,
    close_price: float,
    target_pct: float,
    trading_cost_pct: float = DEFAULT_TRADING_COST_PCT,
) -> DayResult:
    """Advance the account by one trading day.

    `state` is the account at the previous close and `target_pct` is the
    position the previous day's signal asked for. The old position is held
    overnight, the order fills at today's open, and the new position is held
    to today's close. Changing the position pays `trading_cost_pct` on the
    fraction of the account traded.

    Like the backtest, this treats a position as a fraction of the account
    rather than a share count, so `position_value` is that fraction of the
    closing equity.
    """
    _require_positive_price("prev_close", prev_close)
    _require_positive_price("open_price", open_price)
    _require_positive_price("close_price", close_price)

    if not 0.0 <= target_pct <= 1.0:
        raise ValueError("target_pct must be between 0 and 1.")

    if trading_cost_pct < 0:
        raise ValueError("trading_cost_pct cannot be negative.")

    held = state.position_pct

    # Same arithmetic, in the same order, as the loop in run_backtest.
    overnight_return = (open_price / prev_close) - 1
    open_to_close_return = (close_price / open_price) - 1
    cost_pct = abs(target_pct - held) * trading_cost_pct
    daily_return = held * overnight_return + target_pct * open_to_close_return - cost_pct

    equity = state.equity * (1 + daily_return)
    position_value = target_pct * equity

    return DayResult(
        position_before=held,
        position_after=target_pct,
        traded_pct=abs(target_pct - held),
        traded=target_pct != held,
        cost_pct=cost_pct,
        daily_return=daily_return,
        equity=equity,
        position_value=position_value,
        cash=equity - position_value,
    )
