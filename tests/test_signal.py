import pandas as pd
import pytest
from fastapi.testclient import TestClient

from main import app
from services import signal as signal_service
from services.data import MarketDataUnavailableError, NoPriceDataError
from services.features import compute_macd

client = TestClient(app)

MACD_FIELDS = ("macd_line", "signal_line", "histogram")
NO_MACD = {"macd_line": None, "signal_line": None, "histogram": None}


def _price_data(close_prices):
    return pd.DataFrame({"Close": close_prices})


def _mock_price_data(monkeypatch, close_prices):
    monkeypatch.setattr(
        signal_service,
        "get_price_data",
        lambda symbol: _price_data(close_prices),
    )


def _rising_series(length=89, start=100.0):
    # Net-upward sawtooth (+2 / -1) so the RSI stays moderate (~67) and does
    # not trip the overbought override, unlike a strictly monotonic series.
    # An odd length ends on an up-tick so the MACD histogram is positive,
    # i.e. momentum confirms the uptrend and the BUY override does not fire.
    prices = []
    value = start
    for i in range(length):
        value += 2 if i % 2 == 0 else -1
        prices.append(value)
    return prices


def _falling_series(length=89, start=250.0):
    # Net-downward sawtooth (-2 / +1) so the RSI stays moderate (~33) and does
    # not trip the oversold override. An odd length ends on a down-tick so the
    # MACD histogram is negative, i.e. momentum confirms the downtrend and the
    # SELL override does not fire.
    prices = []
    value = start
    for i in range(length):
        value += -2 if i % 2 == 0 else 1
        prices.append(value)
    return prices


def test_generate_signal_buy_path(monkeypatch):
    _mock_price_data(monkeypatch, _rising_series())

    result = signal_service.generate_signal(" aapl ")

    assert result["symbol"] == "AAPL"
    assert result["signal"] == "BUY"
    # A BUY carries real conviction and therefore a real position.
    assert result["confidence"] > 0.5
    assert result["decision"]["position_pct"] > 0


def test_generate_signal_buy_sizes_position_from_confidence(monkeypatch):
    # A 2% gap between the averages at 1% daily volatility is a typical BUY:
    # confidence 0.8, which make_decision maps to two thirds of the 10% cap.
    fake_features = pd.DataFrame(
        {
            "Close": [103.0],
            "ma_20": [102.0],
            "ma_50": [100.0],
            "rolling_volatility": [0.01],
            "trend_slope": [0.0],
            "price_position": [0.03],
            "rsi": [55.0],
            "macd_histogram": [0.5],
        }
    )
    _mock_features(monkeypatch, fake_features)

    result = signal_service.generate_signal("aapl", portfolio_value=10000)

    assert result["signal"] == "BUY"
    assert result["confidence"] == 0.8
    assert result["decision"] == {"position_pct": 0.0667, "position_value": 667.0}


def test_generate_signal_exposes_latest_macd_values(monkeypatch):
    prices = _rising_series()
    _mock_price_data(monkeypatch, prices)

    result = signal_service.generate_signal("aapl")

    for field in MACD_FIELDS:
        assert type(result[field]) is float

    macd_line, signal_line, histogram = compute_macd(pd.Series(prices))
    assert result["macd_line"] == pytest.approx(macd_line.iloc[-1])
    assert result["signal_line"] == pytest.approx(signal_line.iloc[-1])
    assert result["histogram"] == pytest.approx(histogram.iloc[-1])
    # The BUY stands only because the exposed histogram confirms it.
    assert result["histogram"] > 0


def test_generate_signal_macd_none_when_unavailable(monkeypatch):
    # Thin history: the MACD columns exist but are NaN on the latest bar.
    fake_features = pd.DataFrame(
        {
            "Close": [150.0],
            "ma_20": [140.0],
            "ma_50": [120.0],
            "rolling_volatility": [0.01],
            "trend_slope": [0.0],
            "price_position": [0.0],
            "rsi": [50.0],
            "macd": [float("nan")],
            "macd_signal": [float("nan")],
            "macd_histogram": [float("nan")],
        }
    )
    _mock_features(monkeypatch, fake_features)

    result = signal_service.generate_signal("aapl")

    for field in MACD_FIELDS:
        assert field in result
        assert result[field] is None


def test_post_signal_response_includes_macd_fields(monkeypatch):
    _mock_price_data(monkeypatch, _rising_series())

    response = client.post("/signal", json={"symbol": "aapl"})

    assert response.status_code == 200
    body = response.json()
    for field in MACD_FIELDS:
        assert isinstance(body[field], float)


def test_post_signal_response_macd_null_for_thin_history(monkeypatch):
    _mock_price_data(monkeypatch, [100.0, 101.0, 102.0])

    response = client.post("/signal", json={"symbol": "tsla"})

    assert response.status_code == 200
    body = response.json()
    for field in MACD_FIELDS:
        assert field in body
        assert body[field] is None


def test_generate_signal_exposes_latest_rsi_value(monkeypatch):
    # The raw 14-day RSI is reported, not the neutral 50 the overrides fall
    # back to.
    fake_features = pd.DataFrame(
        {
            "Close": [103.0],
            "ma_20": [102.0],
            "ma_50": [100.0],
            "rolling_volatility": [0.01],
            "trend_slope": [0.0],
            "price_position": [0.03],
            "rsi": [57.34],
            "macd_histogram": [0.5],
        }
    )
    _mock_features(monkeypatch, fake_features)

    result = signal_service.generate_signal("aapl")

    assert result["rsi"] == 57.34


def test_generate_signal_rsi_null_but_override_stays_neutral(monkeypatch):
    # Thin history: RSI is NaN. The response reports null, yet the BUY stands
    # because the overbought override still reads a neutral 50 internally.
    fake_features = pd.DataFrame(
        {
            "Close": [103.0],
            "ma_20": [102.0],
            "ma_50": [100.0],
            "rolling_volatility": [0.01],
            "trend_slope": [0.0],
            "price_position": [0.03],
            "rsi": [float("nan")],
            "macd_histogram": [0.5],
        }
    )
    _mock_features(monkeypatch, fake_features)

    result = signal_service.generate_signal("aapl")

    assert result["rsi"] is None
    assert result["signal"] == "BUY"


def test_post_signal_response_includes_rsi_field(monkeypatch):
    _mock_price_data(monkeypatch, _rising_series())

    response = client.post("/signal", json={"symbol": "aapl"})

    assert response.status_code == 200
    assert isinstance(response.json()["rsi"], float)


def test_post_signal_no_price_data_returns_404(monkeypatch):
    def raise_no_data(symbol):
        raise NoPriceDataError(f"No price data found for symbol: {symbol}")

    monkeypatch.setattr(signal_service, "get_price_data", raise_no_data)

    response = client.post("/signal", json={"symbol": "unknown"})

    assert response.status_code == 404
    assert response.json() == {"detail": "No price data found for symbol: UNKNOWN"}


def test_post_signal_market_data_unavailable_returns_503(monkeypatch):
    def raise_unavailable(symbol):
        raise MarketDataUnavailableError(
            f"Market data for {symbol} is temporarily unavailable. Try again shortly."
        )

    monkeypatch.setattr(signal_service, "get_price_data", raise_unavailable)

    response = client.post("/signal", json={"symbol": "aapl"})

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Market data for AAPL is temporarily unavailable. Try again shortly."
    }
    assert response.headers["retry-after"] == "30"


def test_generate_signal_sell_path(monkeypatch):
    _mock_price_data(monkeypatch, _falling_series())

    result = signal_service.generate_signal("msft")

    assert result["symbol"] == "MSFT"
    assert result["signal"] == "SELL"
    assert result["confidence"] >= 0.5


def _mock_features(monkeypatch, fake_features):
    monkeypatch.setattr(
        signal_service,
        "get_price_data",
        lambda symbol: _price_data(list(range(100, 160))),
    )
    monkeypatch.setattr(
        signal_service,
        "build_features",
        lambda data: fake_features,
    )


def test_generate_signal_rsi_overbought_downgrades_buy(monkeypatch):
    # ma_20 > ma_50 would be BUY, but RSI > 70 forces HOLD.
    fake_features = pd.DataFrame(
        {
            "Close": [150.0],
            "ma_20": [140.0],
            "ma_50": [120.0],
            "rolling_volatility": [0.01],
            "trend_slope": [0.0],
            "price_position": [0.0],
            "rsi": [75.0],
        }
    )
    _mock_features(monkeypatch, fake_features)

    result = signal_service.generate_signal("aapl")

    assert result["signal"] == "HOLD"


def test_generate_signal_rsi_oversold_downgrades_sell(monkeypatch):
    # ma_20 < ma_50 would be SELL, but RSI < 30 forces HOLD.
    fake_features = pd.DataFrame(
        {
            "Close": [110.0],
            "ma_20": [120.0],
            "ma_50": [140.0],
            "rolling_volatility": [0.01],
            "trend_slope": [0.0],
            "price_position": [-0.2],
            "rsi": [25.0],
        }
    )
    _mock_features(monkeypatch, fake_features)

    result = signal_service.generate_signal("msft")

    assert result["signal"] == "HOLD"


def test_generate_signal_macd_disagreement_downgrades_buy(monkeypatch):
    # ma_20 > ma_50 would be BUY, but a negative MACD histogram (bearish
    # momentum) disagrees with the crossover and forces HOLD.
    fake_features = pd.DataFrame(
        {
            "Close": [150.0],
            "ma_20": [140.0],
            "ma_50": [120.0],
            "rolling_volatility": [0.01],
            "trend_slope": [0.0],
            "price_position": [0.0],
            "rsi": [50.0],
            "macd_histogram": [-0.5],
        }
    )
    _mock_features(monkeypatch, fake_features)

    result = signal_service.generate_signal("aapl")

    assert result["signal"] == "HOLD"


def test_generate_signal_macd_disagreement_downgrades_sell(monkeypatch):
    # ma_20 < ma_50 would be SELL, but a positive MACD histogram (bullish
    # momentum) disagrees with the crossover and forces HOLD.
    fake_features = pd.DataFrame(
        {
            "Close": [110.0],
            "ma_20": [120.0],
            "ma_50": [140.0],
            "rolling_volatility": [0.01],
            "trend_slope": [0.0],
            "price_position": [-0.2],
            "rsi": [50.0],
            "macd_histogram": [0.5],
        }
    )
    _mock_features(monkeypatch, fake_features)

    result = signal_service.generate_signal("msft")

    assert result["signal"] == "HOLD"


def test_generate_signal_macd_agreement_keeps_buy(monkeypatch):
    # A positive MACD histogram agrees with the bullish crossover, so the
    # BUY stands.
    fake_features = pd.DataFrame(
        {
            "Close": [150.0],
            "ma_20": [140.0],
            "ma_50": [120.0],
            "rolling_volatility": [0.01],
            "trend_slope": [0.0],
            "price_position": [0.0],
            "rsi": [50.0],
            "macd_histogram": [0.5],
        }
    )
    _mock_features(monkeypatch, fake_features)

    result = signal_service.generate_signal("aapl")

    assert result["signal"] == "BUY"


def test_generate_signal_missing_macd_keeps_buy(monkeypatch):
    # MACD is optional: when the histogram is absent the neutral default
    # leaves the crossover signal untouched.
    fake_features = pd.DataFrame(
        {
            "Close": [150.0],
            "ma_20": [140.0],
            "ma_50": [120.0],
            "rolling_volatility": [0.01],
            "trend_slope": [0.0],
            "price_position": [0.0],
            "rsi": [50.0],
        }
    )
    _mock_features(monkeypatch, fake_features)

    result = signal_service.generate_signal("aapl")

    assert result["signal"] == "BUY"


def test_generate_signal_hold_path(monkeypatch):
    _mock_price_data(monkeypatch, [100.0] * 60)

    result = signal_service.generate_signal("spy")

    assert result == {
        "symbol": "SPY",
        "signal": "HOLD",
        "confidence": 0.5,
        # A flat series has no gains or losses, so RSI is undefined (null).
        "rsi": None,
        # A flat series has a well-defined, zero MACD.
        "macd_line": 0.0,
        "signal_line": 0.0,
        "histogram": 0.0,
        "decision": {"position_pct": 0.0, "position_value": 0.0},
    }


def test_generate_signal_insufficient_data_fallback(monkeypatch):
    _mock_price_data(monkeypatch, [100.0, 101.0, 102.0])

    result = signal_service.generate_signal("tsla")

    assert result == {
        "symbol": "TSLA",
        "signal": "HOLD",
        "confidence": 0.5,
        "rsi": None,
        **NO_MACD,
        "decision": {"position_pct": 0.0, "position_value": 0.0},
    }


def test_generate_signal_nan_feature_fallback(monkeypatch):
    _mock_price_data(monkeypatch, [float("nan")] * 60)

    result = signal_service.generate_signal("nvda")

    assert result == {
        "symbol": "NVDA",
        "signal": "HOLD",
        "confidence": 0.5,
        "rsi": None,
        **NO_MACD,
        "decision": {"position_pct": 0.0, "position_value": 0.0},
    }


def test_generate_signal_uses_latest_row_when_it_is_complete(monkeypatch):
    # Two complete rows: the older one would be a SELL, the latest is a BUY.
    fake_features = pd.DataFrame(
        {
            "Close": [97.0, 103.0],
            "ma_20": [98.0, 102.0],
            "ma_50": [100.0, 100.0],
            "rolling_volatility": [0.01, 0.01],
            "trend_slope": [0.0, 0.0],
            "price_position": [-0.03, 0.03],
            "rsi": [45.0, 55.0],
            "macd_histogram": [-0.5, 0.5],
        }
    )
    _mock_features(monkeypatch, fake_features)

    result = signal_service.generate_signal("aapl")

    assert result["signal"] == "BUY"
    assert result["confidence"] == 0.8


def test_generate_signal_falls_back_to_last_complete_row(monkeypatch):
    # The latest row is missing required features, so the signal comes from
    # the most recent row that has them all.
    fake_features = pd.DataFrame(
        {
            "Close": [103.0, 104.0],
            "ma_20": [102.0, 103.0],
            "ma_50": [100.0, float("nan")],
            "rolling_volatility": [0.01, 0.01],
            "trend_slope": [0.0, 0.0],
            "price_position": [0.03, float("nan")],
            "rsi": [55.0, 56.0],
            "macd_histogram": [0.5, 0.5],
        }
    )
    _mock_features(monkeypatch, fake_features)

    result = signal_service.generate_signal("aapl")

    assert result["signal"] == "BUY"
    assert result["confidence"] == 0.8


# compute_confidence measures the gap between the moving averages in units of
# daily volatility and maps it linearly onto [0.5, 0.95], reaching 0.95 once
# the gap is FULL_CONFIDENCE_STRENGTH (3) daily standard deviations wide.


def test_confidence_is_floor_when_averages_coincide():
    assert signal_service.compute_confidence(100.0, 100.0, 0.01) == 0.5


def test_confidence_rises_linearly_with_gap_in_volatility_units():
    # 1% gap at 1% daily vol is one of the three units: 0.5 + 0.45 / 3
    assert signal_service.compute_confidence(101.0, 100.0, 0.01) == 0.65
    # 2% gap at 1% daily vol is two units: 0.5 + 0.45 * 2 / 3
    assert signal_service.compute_confidence(102.0, 100.0, 0.01) == 0.8


def test_confidence_reaches_cap_at_full_strength_and_stays_there():
    assert signal_service.FULL_CONFIDENCE_STRENGTH == 3.0
    assert signal_service.compute_confidence(103.0, 100.0, 0.01) == 0.95
    assert signal_service.compute_confidence(130.0, 100.0, 0.01) == 0.95


def test_confidence_depends_on_gap_relative_to_volatility():
    # A 4% gap in a market that moves 2% a day is exactly as decisive as a
    # 2% gap in one that moves 1% a day, so a volatile symbol is not
    # favoured over a calm one just for having wider raw gaps.
    calm = signal_service.compute_confidence(102.0, 100.0, 0.01)
    volatile = signal_service.compute_confidence(104.0, 100.0, 0.02)
    assert calm == volatile == 0.8
    # The same raw gap in a choppier market earns less confidence.
    assert signal_service.compute_confidence(102.0, 100.0, 0.02) < calm


def test_confidence_is_symmetric_for_bearish_gaps():
    bullish = signal_service.compute_confidence(102.0, 100.0, 0.01)
    bearish = signal_service.compute_confidence(98.0, 100.0, 0.01)
    assert bullish == bearish


def test_confidence_zero_volatility_with_gap_is_cap():
    # A perfectly steady trend has no noise to measure the gap against.
    assert signal_service.compute_confidence(101.0, 100.0, 0.0) == 0.95


def test_confidence_zero_volatility_without_gap_is_floor():
    assert signal_service.compute_confidence(100.0, 100.0, 0.0) == 0.5


def test_generate_signal_invalid_ma_50_fallback(monkeypatch):
    price_data = _price_data(list(range(100, 160)))
    fake_features = pd.DataFrame(
        {
            "Close": [150.0],
            "ma_20": [120.0],
            "ma_50": [0.0],
            "rolling_volatility": [0.01],
        }
    )

    monkeypatch.setattr(
        signal_service,
        "get_price_data",
        lambda symbol: price_data,
    )
    monkeypatch.setattr(
        signal_service,
        "build_features",
        lambda data: fake_features,
    )

    result = signal_service.generate_signal("qqq")

    assert result == {
        "symbol": "QQQ",
        "signal": "HOLD",
        "confidence": 0.5,
        "rsi": None,
        **NO_MACD,
        "decision": {"position_pct": 0.0, "position_value": 0.0},
    }
