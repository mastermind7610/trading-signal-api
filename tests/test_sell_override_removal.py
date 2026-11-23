"""The four SELL overrides, kept as a copy so their effect can be measured.

They only ever turned a bearish crossover (SELL) into HOLD, and the strategy
is long-only, so both mean cash. RETIRED_SELL_OVERRIDES is a verbatim copy of
the four checks in the order services/signal.py applies them, and
apply_retired_sell_overrides rebuilds that behaviour on top of any signal
result. The test here shows the copy makes exactly the decisions the signal
code makes, on every day of seeded histories where each override fires.
"""

import pandas as pd
import pytest

from ledger_samples import sample_prices
from services import signal as signal_service
from services.features import build_features
from services.signal import REQUIRED_FEATURE_COLUMNS, generate_signal_from_features

# Code and condition of each SELL override, in the order the signal checks them.
RETIRED_SELL_OVERRIDES = (
    ("sell_vetoed_trend_rising", lambda inputs: inputs["trend_slope"] > 0.01),
    ("sell_vetoed_price_above_ma50", lambda inputs: inputs["price_position"] > 0.05),
    ("sell_vetoed_oversold", lambda inputs: inputs["rsi"] < 30),
    ("sell_vetoed_macd_bullish", lambda inputs: inputs["macd_histogram"] > 0),
)
RETIRED_CODES = {code for code, _ in RETIRED_SELL_OVERRIDES}

# Seeded histories on which every SELL override fires at least once, and a
# shorter one, for the day-by-day ledger run, on which three of them do.
BACKTEST_HISTORIES = [(1500, 3), (1500, 4)]
DAILY_HISTORY = (300, 2)


def _override_inputs(features: pd.DataFrame) -> dict:
    """The values the overrides read, with the signal code's neutral defaults."""
    row = signal_service._latest_complete_row(features)
    rsi = signal_service._safe_float(row.get("rsi"))
    histogram = signal_service._safe_float(row.get("macd_histogram"))
    return {
        "trend_slope": signal_service._safe_float(row.get("trend_slope")) or 0.0,
        "price_position": signal_service._safe_float(row.get("price_position")) or 0.0,
        "rsi": 50.0 if rsi is None else rsi,
        "macd_histogram": 0.0 if histogram is None else histogram,
    }


def retired_sell_override(features: pd.DataFrame) -> str | None:
    """The code of the first SELL override whose condition holds, or None."""
    inputs = _override_inputs(features)
    return next((code for code, holds in RETIRED_SELL_OVERRIDES if holds(inputs)), None)


def apply_retired_sell_overrides(result: dict, features: pd.DataFrame) -> dict:
    """A signal result with the SELL overrides applied, as the signal code does."""
    if result["signal"] != "SELL":
        return result

    code = retired_sell_override(features)
    if code is None:
        return result

    return {
        **result,
        "signal": "HOLD",
        "reason": code,
        "confidence": signal_service.DEFAULT_HOLD_CONFIDENCE,
    }


def with_retired_sell_overrides(symbol, features, log_decision=True):
    """generate_signal_from_features with the SELL overrides applied on top."""
    result = generate_signal_from_features(symbol, features, log_decision=log_decision)
    return apply_retired_sell_overrides(result, features)


def signal_days(length: int, seed: int):
    """Each day's one-row features and signal, from the backtest's first day."""
    features = build_features(sample_prices(length=length, seed=seed))
    start = int(features[REQUIRED_FEATURE_COLUMNS].notna().all(axis=1).to_numpy().argmax())
    for index in range(start, len(features) - 1):
        row = features.iloc[index : index + 1]
        yield row, generate_signal_from_features("TEST", row, log_decision=False)


@pytest.mark.parametrize("length, seed", [*BACKTEST_HISTORIES, DAILY_HISTORY])
def test_copy_makes_the_signal_codes_sell_decisions(length, seed):
    fired = set()
    bearish_days = 0

    for row, result in signal_days(length, seed):
        if result["reason"] not in RETIRED_CODES | {"ma_crossover_bearish"}:
            continue

        # Every bearish crossover the code either kept or downgraded: the copy
        # must name the same override, or none where the code kept the SELL.
        bearish_days += 1
        expected = retired_sell_override(row)
        assert result["reason"] == (expected or "ma_crossover_bearish")

        if expected is None:
            assert result["signal"] == "SELL"
        else:
            fired.add(expected)
            assert result["signal"] == "HOLD"
            assert result["confidence"] == signal_service.DEFAULT_HOLD_CONFIDENCE

    assert bearish_days > 0
    if (length, seed) in BACKTEST_HISTORIES:
        assert fired == RETIRED_CODES
    else:
        assert len(fired) >= 3
