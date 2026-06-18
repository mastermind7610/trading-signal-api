import pytest

from services.decisions import make_decision, MAX_POSITION_PCT


def test_hold_always_zero():
    result = make_decision("HOLD", 0.9, 10000)
    assert result["position_pct"] == 0.0
    assert result["position_value"] == 0.0


def test_buy_min_confidence_is_zero():
    result = make_decision("BUY", 0.5, 10000)
    assert result["position_pct"] == 0.0
    assert result["position_value"] == 0.0


def test_buy_max_confidence_is_max_position():
    result = make_decision("BUY", 0.95, 10000)
    assert result["position_pct"] == pytest.approx(MAX_POSITION_PCT)
    assert result["position_value"] == pytest.approx(1000.0)


def test_sell_scales_same_as_buy():
    buy = make_decision("BUY", 0.72, 10000)
    sell = make_decision("SELL", 0.72, 10000)
    assert buy["position_pct"] == sell["position_pct"]


def test_position_value_scales_with_portfolio():
    small = make_decision("BUY", 0.95, 5000)
    large = make_decision("BUY", 0.95, 20000)
    assert large["position_value"] == pytest.approx(small["position_value"] * 4)


def test_position_pct_never_exceeds_max():
    result = make_decision("BUY", 1.5, 10000)
    assert result["position_pct"] <= MAX_POSITION_PCT
