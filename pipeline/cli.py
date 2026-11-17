"""The daily run from the command line.

    python -m pipeline SPY AAPL

For each symbol this fetches daily prices from Yahoo Finance, sets aside any
bar whose trading day is not over yet, and brings the symbol's ledger in
MongoDB up to date with pipeline.daily.run_daily. It can be run at any time
and any number of times; see run_daily for why that is safe.

Exit status: 0 if every symbol is up to date, 1 if any symbol failed, 2 if
the command line or the configuration is wrong.
"""

import argparse
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

import pandas as pd

from pipeline.daily import run_daily
from pipeline.mongo_repository import (
    MONGODB_URI_ENV_VAR,
    configured_mongodb_uri,
    ledger_repository_from_uri,
)
from pipeline.repository import LedgerEntry, LedgerRepository, LedgerStorageError
from services.data import MarketDataError, get_price_data

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

# How much history each run fetches. The signal needs only 55 bars, but the
# MACD is an exponential average, which never quite forgets the first bar it
# was given, and the fetch window starts one day later each day. After two
# years (about 500 bars) that first bar's weight is 0.926^500, around 2e-17,
# too small to change a signal. So a day gets the same signal whichever day
# it is computed on, and the same one a backtest gives it.
HISTORY_PERIOD = "2y"


def completed_bars(price_data: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """The bars whose trading day is over at `now` (which must have a timezone).

    While a market is open Yahoo Finance already returns a bar for the day,
    with the latest price standing in for the close. Recording that bar
    would be permanent, because a recorded day is never recomputed.

    A day counts as over once the date has changed in the exchange's own
    timezone, which the price index carries. That needs no table of market
    hours and holds for any exchange. The cost is that a day is recorded by
    the first run after midnight there, not the first run after the close.
    An index without a timezone is compared with the date in UTC, which is
    never ahead of an exchange east of it and passes midnight only after the
    close of one to the west.
    """
    index = price_data.index
    if not isinstance(index, pd.DatetimeIndex):
        # Not a table of dated bars; run_daily reports that.
        return price_data

    today = pd.Timestamp(now).tz_convert(index.tz or UTC).date()
    return price_data[index.date < today]


def update_ledger(
    symbol: str,
    repository: LedgerRepository,
    fetch_prices: Callable[..., pd.DataFrame],
    now: datetime,
) -> list[LedgerEntry]:
    """Fetch one symbol's prices and record the days its ledger is missing."""
    price_data = fetch_prices(symbol, period=HISTORY_PERIOD)
    return run_daily(symbol, completed_bars(price_data, now), repository)


def _describe(entry: LedgerEntry) -> str:
    day = entry.day
    return (
        f"{entry.symbol} {entry.trade_date}: {entry.signal} ({entry.reason}), "
        f"position {day.position_after:.2%}, return {day.daily_return:+.4%}, "
        f"equity {day.equity:,.2f}"
    )


def run(
    symbols: Sequence[str],
    repository: LedgerRepository,
    fetch_prices: Callable[..., pd.DataFrame],
    now: datetime,
) -> int:
    """Bring each symbol's ledger up to date and return the exit status.

    `fetch_prices` is called as services.data.get_price_data is, and `now`
    decides which bars are complete; both are arguments so tests can supply
    them. A symbol that fails is reported and the others still run. Running
    the command again retries it: days already recorded are left alone.
    """
    failed = False

    for symbol in symbols:
        try:
            recorded = update_ledger(symbol, repository, fetch_prices, now)
            latest = repository.latest(symbol)
        except (MarketDataError, LedgerStorageError, ValueError) as exc:
            print(f"{symbol}: failed: {exc}", file=sys.stderr)
            failed = True
            continue

        for entry in recorded:
            print(_describe(entry))

        if not recorded:
            if latest is None:
                print(f"{symbol}: nothing to record yet")
            else:
                print(f"{symbol}: up to date, last recorded day {latest.trade_date}")

    return EXIT_FAILED if failed else EXIT_OK


def main(argv: Sequence[str] | None = None, *, now: datetime | None = None) -> int:
    """Run the command line and return the exit status.

    `now` is the moment the newest bar is judged by. It is the current time
    unless given, and is an argument so tests can fix it.
    """
    parser = argparse.ArgumentParser(
        prog="python -m pipeline",
        description="Bring the paper-trading ledger up to date for each symbol.",
        epilog=(
            f"The ledger is kept in MongoDB: set {MONGODB_URI_ENV_VAR} to the "
            "connection string. Running again on the same day records nothing new."
        ),
    )
    parser.add_argument(
        "symbols",
        nargs="+",
        metavar="SYMBOL",
        help="ticker symbol as used by Yahoo Finance, for example SPY",
    )
    arguments = parser.parse_args(argv)

    # Upper-cased as everywhere else, and each symbol run once.
    symbols = list(dict.fromkeys(symbol.strip().upper() for symbol in arguments.symbols))
    if "" in symbols:
        parser.error("a symbol cannot be empty")

    uri = configured_mongodb_uri()
    if uri is None:
        print(
            f"{MONGODB_URI_ENV_VAR} is not set. Set it to the MongoDB connection "
            "string of the ledger database.",
            file=sys.stderr,
        )
        return EXIT_USAGE

    try:
        repository = ledger_repository_from_uri(uri)
    except LedgerStorageError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE

    return run(symbols, repository, get_price_data, now or datetime.now(UTC))
