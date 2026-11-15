"""Regenerate the numbers quoted in the README.

Runs the same walk-forward backtest that /backtest uses for each symbol,
over the same period and trading cost, and prints:

- the run date and the exact window the results cover,
- the "Backtest Results" table rows in README format,
- the example /backtest and /signal responses for the Swagger section.

Usage, from the project root with the virtual environment active:

    python scripts/backtest_report.py
    python scripts/backtest_report.py --period 10y SPY QQQ

Needs internet access: prices come from yfinance.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

# Make the project importable when run as "python scripts/backtest_report.py".
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.backtest import DEFAULT_TRADING_COST_PCT, run_backtest  # noqa: E402
from services.data import get_price_data  # noqa: E402
from services.features import build_features  # noqa: E402
from services.signal import REQUIRED_FEATURE_COLUMNS, generate_signal  # noqa: E402

DEFAULT_SYMBOLS = ("SPY", "AAPL", "MSFT", "NVDA")
PREFERRED_EXAMPLE_SYMBOL = "AAPL"

TABLE_HEADER = (
    "| Symbol | Strategy Return | Buy-and-Hold Return | Sharpe | Max Drawdown "
    "| Avg. Exposure | Trades | BUY / SELL / HOLD days |"
)
TABLE_RULE = (
    "|--------|-----------------|---------------------|--------|--------------"
    "|---------------|--------|------------------------|"
)


def _signal_window(price_data):
    """First and last trading day the backtest scores.

    Mirrors run_backtest: the first day on which every required feature
    exists is the first signal day, and the last close is the last day scored.
    """
    clean = price_data.dropna(subset=["Open", "Close"])
    features = build_features(clean)
    tradeable = features[REQUIRED_FEATURE_COLUMNS].notna().all(axis=1)
    first = tradeable.idxmax() if tradeable.any() else None
    return first, clean.index[-1]


def _table_row(result):
    days = f"{result['buy_signals']} / {result['sell_signals']} / {result['hold_signals']}"
    return (
        f"| {result['symbol']:<6} "
        f"| {result['cumulative_strategy_return']:+.2%}".ljust(26) + " "
        f"| {result['buy_and_hold_return']:+.2%}".ljust(22) + " "
        f"| {result['sharpe_ratio']:.2f}".ljust(9) + " "
        f"| {result['max_drawdown']:.2%}".ljust(15) + " "
        f"| {result['average_exposure']:.2%}".ljust(16) + " "
        f"| {result['trades']:<6} "
        f"| {days:<22} |"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("symbols", nargs="*", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--period", default="5y", help="yfinance period, default 5y")
    parser.add_argument(
        "--trading-cost-pct",
        type=float,
        default=DEFAULT_TRADING_COST_PCT,
        help=f"cost per unit traded, default {DEFAULT_TRADING_COST_PCT}",
    )
    args = parser.parse_args(argv)

    today = date.today().isoformat()
    print(f"Run date: {today}")
    print(f"Period: {args.period}; trading cost: {args.trading_cost_pct:.2%} of the amount traded")
    print()

    results = []
    windows = []
    for symbol in args.symbols:
        price_data = get_price_data(symbol, period=args.period)
        result = run_backtest(symbol, price_data, trading_cost_pct=args.trading_cost_pct)
        first, last = _signal_window(price_data)
        scored_days = result["buy_signals"] + result["sell_signals"] + result["hold_signals"]
        results.append(result)
        windows.append((result["symbol"], first, last, scored_days))

    print("Data window (first signal day to last close; trading days scored):")
    for symbol, first, last, scored_days in windows:
        first_text = first.date().isoformat() if first is not None else "n/a"
        print(f"  {symbol}: {first_text} to {last.date().isoformat()}; {scored_days} days")
    print()

    print("README table:")
    print(TABLE_HEADER)
    print(TABLE_RULE)
    for result in results:
        print(_table_row(result))
    print()

    symbols = [result["symbol"] for result in results]
    example = PREFERRED_EXAMPLE_SYMBOL if PREFERRED_EXAMPLE_SYMBOL in symbols else symbols[0]
    print(f"Example /backtest response ({example}, captured {today}):")
    print(json.dumps(results[symbols.index(example)], indent=2))
    print()
    print(f"Example /signal response ({example}, captured {today}):")
    print(json.dumps(generate_signal(example), indent=2))


if __name__ == "__main__":
    main()
