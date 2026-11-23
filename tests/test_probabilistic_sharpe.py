"""PSR unit check for math_experiments/02_probabilistic_sharpe.py."""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

_PATH = Path(__file__).resolve().parents[1] / "math_experiments" / "02_probabilistic_sharpe.py"
_spec = importlib.util.spec_from_file_location("probabilistic_sharpe_exp", _PATH)
psr = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(psr)


def test_psr_normal_returns_match_analytic():
    mu, sigma, n = 0.001, 0.01, 8_000
    sr_pop = mu / sigma
    analytic = float(
        norm.cdf(sr_pop * np.sqrt(n - 1) / np.sqrt(1.0 + 0.5 * sr_pop**2))
    )
    rng = np.random.default_rng(42)
    returns = pd.Series(rng.normal(mu, sigma, size=n))
    estimated = psr.row_metrics(returns)["PSR"]
    assert abs(estimated - analytic) < 0.02
