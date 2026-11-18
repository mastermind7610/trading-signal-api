"""Check that the research engine reproduces the production backtest.

    python -I research/verify_engine.py

For every symbol, on the tuning window only:

1. Row by row, the full strategy's signal and target position equal what
   services/signal.py and services/decisions.py give for that row.
2. Run through research/engine.py, the full strategy's return, Sharpe
   ratio, drawdown, exposure, trades, costs and signal counts equal
   services/backtest.run_backtest's, to the decimals run_backtest reports.

Exits 1 on any mismatch.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research.config import SYMBOLS, TRADING_COST_PCT  # noqa: E402
from research.engine import (  # noqa: E402
    BUY,
    HOLD,
    SELL,
    TUNING,
    signal_inputs,
    simulate,
    variant_by_name,
    variant_signals,
    variant_targets,
    window_prices,
)
from services.backtest import run_backtest  # noqa: E402
from services.decisions import make_decision  # noqa: E402
from services.features import build_features  # noqa: E402
from services.signal import generate_signal_from_features  # noqa: E402


def _check_symbol(symbol: str) -> list[str]:
    prices, first = window_prices(symbol, TUNING)
    full = variant_by_name("full")
    inputs = signal_inputs(prices)
    signals = variant_signals(inputs, full.overrides)
    targets = variant_targets(inputs, full)
    features = build_features(prices)

    problems = []
    for row in range(first, len(prices) - 1):
        expected = generate_signal_from_features(
            symbol, features.iloc[row : row + 1], log_decision=False
        )
        expected_target = make_decision(expected["signal"], expected["confidence"], 1.0)[
            "position_pct"
        ]
        if expected["signal"] != signals[row] or expected_target != targets[row]:
            problems.append(
                f"{symbol} {prices.index[row].date()}: engine {signals[row]} {targets[row]}, "
                f"production {expected['signal']} {expected_target}"
            )

    production = run_backtest(symbol, prices, trading_cost_pct=TRADING_COST_PCT)
    engine = simulate(prices, targets, first)
    scored = signals[first : len(prices) - 1]
    comparisons = {
        "cumulative_strategy_return": round(engine["total_return"], 4),
        "sharpe_ratio": engine["sharpe"],
        "max_drawdown": engine["max_drawdown"],
        "average_exposure": round(engine["exposure"], 4),
        "trades": engine["trades"],
        "total_trading_costs": round(engine["total_trading_costs"], 6),
        "buy_signals": int((scored == BUY).sum()),
        "sell_signals": int((scored == SELL).sum()),
        "hold_signals": int((scored == HOLD).sum()),
    }
    for key, value in comparisons.items():
        if production[key] != value:
            problems.append(f"{symbol} {key}: engine {value}, run_backtest {production[key]}")

    print(
        f"{symbol}: {len(prices) - 1 - first} signal days, "
        f"{engine['first_return_day']} to {engine['last_return_day']}, "
        f"{'OK' if not problems else f'{len(problems)} mismatches'}"
    )
    return problems


def main() -> int:
    problems = []
    for symbol in SYMBOLS:
        problems += _check_symbol(symbol)

    for problem in problems[:20]:
        print(problem)
    if problems:
        print(f"FAILED: {len(problems)} mismatches")
        return 1

    print("Engine matches services/backtest.py on every symbol")
    return 0


if __name__ == "__main__":
    sys.exit(main())
