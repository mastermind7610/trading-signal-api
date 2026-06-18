import pandas as pd

from services import signal as signal_service


def _price_data(close_prices):
    return pd.DataFrame({"Close": close_prices})


def _mock_price_data(monkeypatch, close_prices):
    monkeypatch.setattr(
        signal_service,
        "get_price_data",
        lambda symbol: _price_data(close_prices),
    )


def _rising_series(length=90, start=100.0):
    # Net-upward sawtooth (+2 / -1) so the RSI stays moderate (~67) and does
    # not trip the overbought override, unlike a strictly monotonic series.
    prices = []
    value = start
    for i in range(length):
        value += 2 if i % 2 == 0 else -1
        prices.append(value)
    return prices


def _falling_series(length=90, start=250.0):
    # Net-downward sawtooth (-2 / +1) so the RSI stays moderate (~33) and does
    # not trip the oversold override.
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
    assert result["confidence"] >= 0.5


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


def test_generate_signal_hold_path(monkeypatch):
    _mock_price_data(monkeypatch, [100.0] * 60)

    result = signal_service.generate_signal("spy")

    assert result == {
        "symbol": "SPY",
        "signal": "HOLD",
        "confidence": 0.5,
        "decision": {"position_pct": 0.0, "position_value": 0.0},
    }


def test_generate_signal_insufficient_data_fallback(monkeypatch):
    _mock_price_data(monkeypatch, [100.0, 101.0, 102.0])

    result = signal_service.generate_signal("tsla")

    assert result == {
        "symbol": "TSLA",
        "signal": "HOLD",
        "confidence": 0.5,
        "decision": {"position_pct": 0.0, "position_value": 0.0},
    }


def test_generate_signal_nan_feature_fallback(monkeypatch):
    _mock_price_data(monkeypatch, [float("nan")] * 60)

    result = signal_service.generate_signal("nvda")

    assert result == {
        "symbol": "NVDA",
        "signal": "HOLD",
        "confidence": 0.5,
        "decision": {"position_pct": 0.0, "position_value": 0.0},
    }


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
        "decision": {"position_pct": 0.0, "position_value": 0.0},
    }