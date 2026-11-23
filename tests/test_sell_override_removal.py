"""Removing the four SELL overrides changes labels, never money.

The overrides only ever turned a bearish crossover (SELL) into HOLD, and the
strategy is long-only, so both mean cash. RETIRED_SELL_OVERRIDES is a verbatim
copy of the four checks, in the order services/signal.py applied them before
they were removed. The commit that added it, before the removal, tested that
the copy made exactly the signal code's decisions. apply_retired_sell_overrides
rebuilds the old behaviour on top of today's signal, so old and new can be run
side by side on the same prices.

The tests show that on seeded histories where every override would fire:
- every bearish crossover now reports SELL at the crossover's confidence;
- the backtest holds the same position on every day and reports the same
  figures, apart from the SELL and HOLD day counts;
- the daily ledger records the same money values on every day, and only the
  days the old rules relabelled have a different signal, reason or confidence.
"""

import pandas as pd
import pytest

from ledger_samples import bar_dates, bars_through, sample_prices
from pipeline import daily as daily_run
from pipeline.daily import run_daily
from pipeline.repository import InMemoryLedgerRepository
from services import backtest as backtest_service
from services import signal as signal_service
from services.backtest import run_backtest
from services.decisions import make_decision
from services.features import build_features
from services.signal import (
    REQUIRED_FEATURE_COLUMNS,
    compute_confidence,
    generate_signal_from_features,
)

# Code and condition of each retired SELL override, in the order the signal
# checked them.
RETIRED_SELL_OVERRIDES = (
    ("sell_vetoed_trend_rising", lambda inputs: inputs["trend_slope"] > 0.01),
    ("sell_vetoed_price_above_ma50", lambda inputs: inputs["price_position"] > 0.05),
    ("sell_vetoed_oversold", lambda inputs: inputs["rsi"] < 30),
    ("sell_vetoed_macd_bullish", lambda inputs: inputs["macd_histogram"] > 0),
)
RETIRED_CODES = {code for code, _ in RETIRED_SELL_OVERRIDES}

# Seeded histories on which every retired override would fire at least once,
# and a shorter one, for the day-by-day ledger run, on which three of them do.
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
    """The code of the first retired SELL override whose condition holds, or None."""
    inputs = _override_inputs(features)
    return next((code for code, holds in RETIRED_SELL_OVERRIDES if holds(inputs)), None)


def apply_retired_sell_overrides(result: dict, features: pd.DataFrame) -> dict:
    """A signal result with the retired SELL overrides applied, as they were."""
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
    """generate_signal_from_features as it was with the four SELL overrides."""
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
def test_every_bearish_crossover_now_reports_sell(length, seed):
    would_have_fired = set()
    bearish_days = 0

    for row, result in signal_days(length, seed):
        assert result["reason"] not in RETIRED_CODES

        if result["reason"] != "ma_crossover_bearish":
            continue

        bearish_days += 1
        latest = row.iloc[-1]
        assert result["signal"] == "SELL"
        assert result["confidence"] == compute_confidence(
            latest["ma_20"], latest["ma_50"], latest["rolling_volatility"]
        )
        assert make_decision(result["signal"], result["confidence"], 1.0)["position_pct"] == 0.0

        code = retired_sell_override(row)
        if code is not None:
            would_have_fired.add(code)

    assert bearish_days > 0
    # The days below are the ones the old rules would have relabelled HOLD.
    if (length, seed) in BACKTEST_HISTORIES:
        assert would_have_fired == RETIRED_CODES
    else:
        assert len(would_have_fired) >= 3


def _backtest_with_positions(monkeypatch, prices, signal_function):
    """run_backtest's result and the position it targets on each day."""
    positions = []

    def recording(signal, confidence, portfolio_value):
        # The original make_decision, not whatever an earlier call patched in.
        decision = make_decision(signal, confidence, portfolio_value)
        positions.append(decision["position_pct"])
        return decision

    monkeypatch.setattr(backtest_service, "make_decision", recording)
    monkeypatch.setattr(backtest_service, "generate_signal_from_features", signal_function)
    return run_backtest("TEST", prices), positions


@pytest.mark.parametrize("length, seed", BACKTEST_HISTORIES)
def test_removing_the_overrides_changes_no_backtest_figure(monkeypatch, length, seed):
    prices = sample_prices(length=length, seed=seed)

    now, now_positions = _backtest_with_positions(
        monkeypatch, prices, generate_signal_from_features
    )
    before, before_positions = _backtest_with_positions(
        monkeypatch, prices, with_retired_sell_overrides
    )

    # The same position every day means the same return every day.
    assert now_positions == before_positions

    labels = {"sell_signals", "hold_signals"}
    assert {key: value for key, value in now.items() if key not in labels} == {
        key: value for key, value in before.items() if key not in labels
    }

    relabelled = now["sell_signals"] - before["sell_signals"]
    assert relabelled > 0
    assert now["hold_signals"] == before["hold_signals"] - relabelled


def _daily_ledger(prices: pd.DataFrame):
    """The ledger from running the daily run once per day, as in production."""
    ready = build_features(prices)[REQUIRED_FEATURE_COLUMNS].notna().all(axis=1).to_numpy()
    start = int(ready.argmax())
    repository = InMemoryLedgerRepository()
    for day in bar_dates(prices)[start + 1 :]:
        run_daily("TEST", bars_through(prices, day), repository)
    return repository.history("TEST")


def test_removing_the_overrides_changes_no_ledger_value(monkeypatch):
    length, seed = DAILY_HISTORY
    prices = sample_prices(length=length, seed=seed)

    now = _daily_ledger(prices)
    monkeypatch.setattr(daily_run, "generate_signal_from_features", with_retired_sell_overrides)
    before = _daily_ledger(prices)

    assert len(now) == len(before) > 0
    relabelled = 0

    for entry, old in zip(now, before, strict=True):
        # Positions, fill, cost, return, equity, position value and cash.
        assert entry.day == old.day
        assert (entry.trade_date, entry.signal_date) == (old.trade_date, old.signal_date)
        assert (entry.prev_close, entry.open_price, entry.close_price) == (
            old.prev_close,
            old.open_price,
            old.close_price,
        )

        if old.reason in RETIRED_CODES:
            relabelled += 1
            assert old.signal == "HOLD"
            assert old.confidence == signal_service.DEFAULT_HOLD_CONFIDENCE
            assert (entry.signal, entry.reason) == ("SELL", "ma_crossover_bearish")
            assert entry.day.position_after == 0.0
        else:
            assert (entry.signal, entry.reason, entry.confidence) == (
                old.signal,
                old.reason,
                old.confidence,
            )

    assert relabelled > 0
