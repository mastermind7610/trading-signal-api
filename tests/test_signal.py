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


def test_generate_signal_buy_path(monkeypatch):
    _mock_price_data(monkeypatch, list(range(100, 160)))

    result = signal_service.generate_signal(" aapl ")

    assert result["symbol"] == "AAPL"
    assert result["signal"] == "BUY"
    assert result["confidence"] >= 0.5


def test_generate_signal_sell_path(monkeypatch):
    _mock_price_data(monkeypatch, list(range(160, 100, -1)))

    result = signal_service.generate_signal("msft")

    assert result["symbol"] == "MSFT"
    assert result["signal"] == "SELL"
    assert result["confidence"] >= 0.5


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