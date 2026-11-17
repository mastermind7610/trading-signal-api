"""Sample prices and ledger entries shared by the ledger tests. Not a test file."""

import random
from datetime import date, timedelta

import pandas as pd

from pipeline.ledger import AccountState, apply_day
from pipeline.repository import LedgerEntry

# US Thanksgiving 2026: a weekday with no trading, so no price bar.
HOLIDAY = date(2026, 11, 26)
DAY_BEFORE_HOLIDAY = date(2026, 11, 25)
DAY_AFTER_HOLIDAY = date(2026, 11, 27)


def sample_prices(length=120, seed=2, end="2026-12-04"):
    """Deterministic noisy daily bars on weekdays ending at `end`, skipping
    the holiday. Opens gap away from the previous close.

    The default seed is one whose last two weeks buy and sell, so the tests
    on those days are not comparing an account that sat in cash throughout.
    """
    days = pd.bdate_range(end=end, periods=length + 1)
    days = days[days != pd.Timestamp(HOLIDAY)][-length:]

    rng = random.Random(seed)
    opens, closes = [], []
    close = 100.0
    for _ in range(length):
        open_price = close * (1 + rng.gauss(0.0, 0.004))
        close = open_price * (1 + rng.gauss(0.0005, 0.015))
        opens.append(round(open_price, 2))
        closes.append(round(close, 2))

    return pd.DataFrame({"Open": opens, "Close": closes}, index=days)


def bars_through(price_data, day):
    """The bars a run on `day` would see: everything up to and including it."""
    return price_data[price_data.index <= pd.Timestamp(day)]


def bar_dates(price_data):
    return [timestamp.date() for timestamp in price_data.index]


def sample_entry(symbol, trade_date):
    """A ledger entry for the given day.

    The prices are chosen so the account's figures do not come out as round
    numbers: a store that loses float precision fails an equality check.
    """
    day = apply_day(
        AccountState(equity=10_000.0, position_pct=0.0644),
        prev_close=100.13,
        open_price=99.87,
        close_price=101.37,
        target_pct=0.0733,
        trading_cost_pct=0.001,
    )
    return LedgerEntry(
        symbol=symbol,
        trade_date=trade_date,
        signal_date=trade_date - timedelta(days=1),
        signal="BUY",
        confidence=0.83,
        reason="ma_crossover_bullish",
        prev_close=100.13,
        open_price=99.87,
        close_price=101.37,
        day=day,
    )
