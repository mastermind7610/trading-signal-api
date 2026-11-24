"""The plain-English explanation on /signal (services/explanations.py).

Unit tests pin the wording for each reason code from hand-built facts. The
wiring tests go through services.signal, and check that the text quotes the
values and thresholds the decision itself used, on every day of two long
sample histories.
"""

import re
from dataclasses import replace
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from ledger_samples import sample_prices
from main import app
from services import signal as signal_service
from services.decisions import make_decision
from services.explanations import SignalFacts, explain_signal
from services.features import build_features

client = TestClient(app)

README = Path(__file__).resolve().parent.parent / "README.md"

FACTS = SignalFacts(
    bars=120,
    min_bars=50,
    trend_falling_slope=-0.01,
    overbought_rsi=70.0,
    full_confidence_strength=3.0,
    as_of=date(2026, 11, 20),
    gap=0.02,
    strength=2.0,
    rolling_volatility=0.01,
    trend_slope=0.003,
    rsi=57.34,
    macd_histogram=0.7352,
)

BULLISH_CROSSOVER = (
    "The 20-day average is 2.0% above the 50-day, 2.0 times the typical daily "
    "move of 1.0%: a bullish crossover"
)


def _explain(reason, signal="HOLD", confidence=0.5, position_pct=0.0, **values):
    return explain_signal(signal, reason, confidence, position_pct, replace(FACTS, **values))


def test_bullish_crossover_names_each_check_and_the_position():
    text = _explain("ma_crossover_bullish", signal="BUY", confidence=0.8, position_pct=0.0667)

    assert text == (
        f"BUY as of 2026-11-20. {BULLISH_CROSSOVER}, confidence 0.80 (3 times or "
        "more earns the 0.95 cap). The trend, RSI and MACD checks all passed: the "
        "50-day average moved +0.3% over 5 days, RSI is 57.3 (limit 70), and the "
        "MACD histogram is +0.74. Suggested position: 6.7% of the portfolio, at "
        "most 10%."
    )


def test_bullish_crossover_says_when_rsi_and_macd_are_not_available():
    text = _explain(
        "ma_crossover_bullish",
        signal="BUY",
        confidence=0.8,
        position_pct=0.0667,
        rsi=None,
        macd_histogram=None,
    )

    assert "RSI is not available yet" in text
    assert "the MACD histogram is not available yet" in text


def test_bearish_crossover_says_sell_means_cash():
    text = _explain("ma_crossover_bearish", signal="SELL", confidence=0.8, gap=-0.02)

    assert text == (
        "SELL as of 2026-11-20. The 20-day average is 2.0% below the 50-day, 2.0 "
        "times the typical daily move of 1.0%: a bearish crossover, confidence "
        "0.80. The strategy is long-only, so SELL means holding no position (cash)."
    )


@pytest.mark.parametrize(
    "reason, values, because",
    [
        (
            "buy_vetoed_trend_falling",
            {"trend_slope": -0.012},
            "the 50-day average fell 1.2% over 5 days, more than the 1% limit",
        ),
        (
            "buy_vetoed_overbought",
            {"rsi": 73.2},
            "RSI is 73.2, above the overbought limit of 70",
        ),
        (
            "buy_vetoed_macd_bearish",
            {"macd_histogram": -0.74},
            "the MACD histogram is -0.74, below zero, so momentum disagrees with the "
            "crossover",
        ),
    ],
)
def test_a_vetoed_buy_names_the_one_veto_responsible(reason, values, because):
    text = _explain(reason, **values)

    assert text == (
        f"HOLD as of 2026-11-20. {BULLISH_CROSSOVER}, but the BUY was held back "
        f"because {because}. No position."
    )


def test_veto_text_quotes_the_thresholds_it_is_given():
    assert "above the overbought limit of 65" in _explain(
        "buy_vetoed_overbought", rsi=67.0, overbought_rsi=65.0
    )
    assert "more than the 2% limit" in _explain(
        "buy_vetoed_trend_falling", trend_slope=-0.025, trend_falling_slope=-0.02
    )


def test_zero_volatility_has_no_strength_to_quote():
    text = _explain(
        "ma_crossover_bearish",
        signal="SELL",
        confidence=0.95,
        gap=-0.02,
        strength=float("inf"),
        rolling_volatility=0.0,
    )

    assert "with no day-to-day price movement to measure the gap against" in text
    assert "inf" not in text


def test_no_crossover():
    assert _explain("no_ma_crossover", gap=0.0, strength=0.0) == (
        "HOLD as of 2026-11-20. The 20-day and 50-day averages are equal, so there "
        "is no crossover. No position."
    )


def test_too_little_history_counts_the_bars():
    no_row = SignalFacts(
        bars=1,
        min_bars=50,
        trend_falling_slope=-0.01,
        overbought_rsi=70.0,
        full_confidence_strength=3.0,
    )

    assert explain_signal("HOLD", "insufficient_price_history", 0.5, 0.0, no_row) == (
        "HOLD. There is only 1 daily bar of price history, and the signal needs at "
        "least 50. No position."
    )


@pytest.mark.parametrize(
    "reason", ["missing_feature_columns", "invalid_feature_values", "invalid_confidence"]
)
def test_unreliable_indicators(reason):
    assert _explain(reason) == (
        "HOLD as of 2026-11-20. The indicators could not be computed reliably from "
        "this price data, so no crossover was read. No position."
    )


def test_an_unknown_reason_code_still_gets_a_truthful_line():
    assert _explain("some_new_code") == (
        "HOLD as of 2026-11-20. Reason code: some_new_code. No position."
    )


def _documented_reason_codes():
    """The codes in the README's Reason codes table, retired ones excluded."""
    text = README.read_text(encoding="utf-8")
    section = text.split("### Reason codes", 1)[1].split("#### Retired reason codes", 1)[0]
    # Every row but the header, whose second cell is "Meaning".
    return re.findall(r"^\| `([a-z_]+)` \| (?!Meaning)", section, flags=re.MULTILINE)


def test_every_documented_reason_code_has_its_own_explanation():
    codes = _documented_reason_codes()

    assert len(codes) == 11
    for code in codes:
        assert "Reason code:" not in _explain(code), code


# Wiring: through services.signal, as /signal runs it.


def _fake_signal_inputs(monkeypatch, **values):
    """Make generate_signal read one dated row of features with these values."""
    row = {
        "Close": 105.0,
        "ma_20": 102.0,
        "ma_50": 100.0,
        "rolling_volatility": 0.01,
        "trend_slope": 0.0,
        "price_position": 0.05,
        "rsi": 50.0,
        "macd_histogram": 0.5,
    }
    row.update(values)
    features = pd.DataFrame([row], index=pd.DatetimeIndex(["2026-11-20"]))
    prices = pd.DataFrame({"Close": [100.0] * 60})

    monkeypatch.setattr(signal_service, "get_price_data", lambda symbol: prices)
    monkeypatch.setattr(signal_service, "build_features", lambda data: features)


def test_signal_explanation_quotes_the_threshold_the_check_used(monkeypatch):
    # Moving the rule's constant moves the check and the text together.
    _fake_signal_inputs(monkeypatch, rsi=65.0)
    monkeypatch.setattr(signal_service, "OVERBOUGHT_RSI", 60.0)

    result = signal_service.generate_signal("aapl")

    assert result["reason"] == "buy_vetoed_overbought"
    assert "RSI is 65.0, above the overbought limit of 60" in result["explanation"]


def test_signal_explanation_is_dated_and_matches_the_response(monkeypatch):
    _fake_signal_inputs(monkeypatch)

    result = signal_service.generate_signal("aapl", portfolio_value=10_000)

    assert result["signal"] == "BUY"
    assert result["explanation"].startswith("BUY as of 2026-11-20. ")
    assert f"confidence {result['confidence']:.2f}" in result["explanation"]
    position = result["decision"]["position_pct"]
    assert f"Suggested position: {position * 100:.1f}% of the portfolio" in result["explanation"]


def test_post_signal_response_includes_the_explanation(monkeypatch):
    _fake_signal_inputs(monkeypatch)

    response = client.post("/signal", json={"symbol": "aapl"})

    assert response.status_code == 200
    assert response.json()["explanation"].startswith("BUY as of 2026-11-20. ")


LEAKED_VALUE = re.compile(r"\b(nan|inf|None)\b")


def test_every_day_of_two_long_histories_is_explained_from_its_own_values():
    seen = set()

    for seed in (3, 4):
        features = build_features(sample_prices(length=1500, seed=seed))

        for index in range(len(features)):
            row = features.iloc[index]
            result = signal_service.generate_signal_from_features(
                "TEST", features.iloc[index : index + 1], log_decision=False
            )
            position = make_decision(result["signal"], result["confidence"], 1.0)
            facts = signal_service._signal_facts(row, index + 1)
            text = explain_signal(
                result["signal"],
                result["reason"],
                result["confidence"],
                position["position_pct"],
                facts,
            )
            reason = result["reason"]
            seen.add(reason)

            assert text.startswith(f"{result['signal']} as of {row.name.date()}. "), text
            assert not LEAKED_VALUE.search(text), text
            assert "Reason code:" not in text, text

            if reason == "ma_crossover_bullish":
                assert f"confidence {result['confidence']:.2f}" in text
            elif reason == "ma_crossover_bearish":
                assert "a bearish crossover" in text
            elif reason == "buy_vetoed_trend_falling":
                assert facts.trend_slope < signal_service.TREND_FALLING_SLOPE
                assert f"fell {abs(facts.trend_slope) * 100:.1f}% over 5 days" in text
            elif reason == "buy_vetoed_overbought":
                assert facts.rsi > signal_service.OVERBOUGHT_RSI
                assert f"RSI is {facts.rsi:.1f}, above the overbought limit of 70" in text
            elif reason == "buy_vetoed_macd_bearish":
                assert facts.macd_histogram < 0
                assert f"the MACD histogram is {facts.macd_histogram:+.2f}, below zero" in text

    # Each of the five crossover outcomes occurs, so no branch passes vacuously.
    assert seen >= {
        "ma_crossover_bullish",
        "ma_crossover_bearish",
        "buy_vetoed_trend_falling",
        "buy_vetoed_overbought",
        "buy_vetoed_macd_bearish",
    }
