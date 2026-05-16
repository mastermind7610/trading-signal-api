import pandas as pd
from fastapi.testclient import TestClient

from main import app
from routes import backtest as backtest_route


client = TestClient(app)


def test_post_backtest_success(monkeypatch):
    price_data = pd.DataFrame({"Close": list(range(100, 161))})

    monkeypatch.setattr(
        backtest_route,
        "get_price_data",
        lambda symbol: price_data,
    )

    response = client.post("/backtest", json={"symbol": "aapl"})

    assert response.status_code == 200

    body = response.json()
    assert body["symbol"] == "AAPL"
    assert body["buy_signals"] > 0
    assert body["sell_signals"] == 0
    assert body["hold_signals"] > 0
    assert body["cumulative_strategy_return"] > 0
    assert body["buy_and_hold_return"] > 0


def test_post_backtest_data_error_returns_400(monkeypatch):
    def raise_value_error(symbol):
        raise ValueError(f"No price data found for symbol: {symbol}")

    monkeypatch.setattr(
        backtest_route,
        "get_price_data",
        raise_value_error,
    )

    response = client.post("/backtest", json={"symbol": "UNKNOWN"})

    assert response.status_code == 400
    assert response.json() == {
        "detail": "No price data found for symbol: UNKNOWN",
    }
