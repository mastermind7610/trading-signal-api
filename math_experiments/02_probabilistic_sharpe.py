"""
Concept: The Probabilistic Sharpe Ratio (Bailey & López de Prado) converts an
observed Sharpe into P(true SR > SR*), adjusting for sample length, skewness,
and kurtosis — so a high SR on few noisy days is not treated as proven skill.

Takeaway: TODO — fill after running
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, norm, skew

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from research.config import RESULTS_DIR, TRADING_COST_PCT  # noqa: E402
from research.engine import (  # noqa: E402
    TUNING,
    signal_inputs,
    simulate,
    variant_by_name,
    variant_targets,
    window_prices,
)

TRADING_DAYS = 252
DEFAULT_SYMBOL = "SPY"


def load_daily_returns(symbol: str, window: str, variant_name: str) -> pd.Series:
    """Daily strategy returns from research.engine.simulate (no accounting copy)."""
    prices, first = window_prices(symbol, window)
    targets = variant_targets(signal_inputs(prices), variant_by_name(variant_name))
    return simulate(prices, targets, first, TRADING_COST_PCT)["returns"]


def sharpe_moments(returns: pd.Series) -> tuple[float, int, float, float]:
    """Non-annualized SR, n, skew g3, raw kurtosis g4 (normal = 3)."""
    r = np.asarray(returns, dtype=float)
    n = len(r)
    std = float(r.std(ddof=1))
    sr = float(r.mean() / std) if n >= 2 and std > 0 else 0.0
    g3 = float(skew(r, bias=False)) if n >= 3 else 0.0
    g4 = float(kurtosis(r, fisher=False, bias=False)) if n >= 4 else 3.0
    return sr, n, g3, g4


def probabilistic_sharpe(
    sr: float, n: int, g3: float, g4: float, sr_star: float = 0.0
) -> float:
    """PSR = Φ((SR − SR*) √(n−1) / √(1 − g3·SR + ((g4−1)/4)·SR²))."""
    if n < 2:
        return float("nan")
    denom = np.sqrt(1.0 - g3 * sr + ((g4 - 1.0) / 4.0) * sr**2)
    if not np.isfinite(denom) or denom <= 0:
        return float("nan")
    return float(norm.cdf((sr - sr_star) * np.sqrt(n - 1) / denom))


def row_metrics(returns: pd.Series) -> dict[str, float | int]:
    sr, n, g3, g4 = sharpe_moments(returns)
    return {
        "SR": sr,
        "ann_SR": sr * np.sqrt(TRADING_DAYS),
        "skew": g3,
        "kurtosis": g4,
        "n": n,
        "PSR": probabilistic_sharpe(sr, n, g3, g4),
    }


def _chosen_variant() -> str:
    path = RESULTS_DIR / "selection.json"
    return json.loads(path.read_text(encoding="utf-8"))["chosen"] if path.exists() else "bare"


def main() -> None:
    strategy = _chosen_variant()
    series = {
        "strategy": load_daily_returns(DEFAULT_SYMBOL, TUNING, strategy),
        "buy-and-hold": load_daily_returns(DEFAULT_SYMBOL, TUNING, "buy_and_hold"),
    }
    print(f"{DEFAULT_SYMBOL} {TUNING} (strategy={strategy})")
    cols = ("SR", "ann_SR", "skew", "kurtosis", "n", "PSR")
    print(f"{'':14}" + "".join(f"{c:>12}" for c in cols))
    for name, returns in series.items():
        m = row_metrics(returns)
        print(
            f"{name:14}"
            f"{m['SR']:12.4f}{m['ann_SR']:12.4f}{m['skew']:12.4f}"
            f"{m['kurtosis']:12.4f}{m['n']:12d}{m['PSR']:12.4f}"
        )


if __name__ == "__main__":
    main()
