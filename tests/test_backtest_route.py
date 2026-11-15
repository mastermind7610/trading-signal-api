import math

import pandas as pd
from fastapi.testclient import TestClient

from main import app
from routes import backtest as backtest_route
from services import backtest as backtest_service
from services.data import MarketDataUnavailableError, NoPriceDataError

client = TestClient(app)


def _rising_series(length=90, start=100.0):
    # Net-upward sawtooth keeps RSI moderate so BUYs are not all suppressed by
    # the overbought override.
    prices = []
    value = start
    for i in range(length):
        value += 2 if i % 2 == 0 else -1
        prices.append(value)
    return prices


def _price_frame(prices):
    return pd.DataFrame({"Open": prices, "Close": prices})


def test_post_backtest_success(monkeypatch):
    price_data = _price_frame(_rising_series())

    monkeypatch.setattr(
        backtest_route,
        "get_price_data",
        lambda symbol, period: price_data,
    )

    response = client.post("/backtest", json={"symbol": "aapl"})

    assert response.status_code == 200

    body = response.json()
    assert body["symbol"] == "AAPL"
    assert body["buy_signals"] > 0
    assert body["sell_signals"] == 0
    assert body["hold_signals"] > 0
    assert body["buy_and_hold_return"] > 0
    # The MACD momentum filter whipsaws this naive crossover strategy on the
    # mean-reverting sawtooth, so we only assert the metrics are computed rather
    # than a positive strategy return (see tests/test_backtest.py).
    assert math.isfinite(body["cumulative_strategy_return"])
    assert math.isfinite(body["sharpe_ratio"])
    assert body["max_drawdown"] <= 0
    assert 0 <= body["average_exposure"] <= 0.1


def test_post_backtest_no_price_data_returns_404(monkeypatch):
    def raise_no_data(symbol, period):
        raise NoPriceDataError(f"No price data found for symbol: {symbol}")

    monkeypatch.setattr(backtest_route, "get_price_data", raise_no_data)

    response = client.post("/backtest", json={"symbol": "unknown"})

    assert response.status_code == 404
    assert response.json() == {"detail": "No price data found for symbol: UNKNOWN"}


def test_post_backtest_market_data_unavailable_returns_503(monkeypatch):
    def raise_unavailable(symbol, period):
        raise MarketDataUnavailableError(
            f"Market data for {symbol} is temporarily unavailable. Try again shortly."
        )

    monkeypatch.setattr(backtest_route, "get_price_data", raise_unavailable)

    response = client.post("/backtest", json={"symbol": "aapl"})

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Market data for AAPL is temporarily unavailable. Try again shortly."
    }
    assert response.headers["retry-after"] == "30"


def test_post_backtest_passes_period_and_trading_cost(monkeypatch):
    seen = {}

    def fake_get_price_data(symbol, period):
        seen["period"] = period
        return _price_frame(_rising_series())

    def fake_run_backtest(symbol, data, trading_cost_pct):
        seen["trading_cost_pct"] = trading_cost_pct
        return backtest_service._empty_result(symbol.upper())

    monkeypatch.setattr(backtest_route, "get_price_data", fake_get_price_data)
    monkeypatch.setattr(backtest_route, "run_backtest", fake_run_backtest)

    response = client.post(
        "/backtest",
        json={"symbol": "aapl", "period": "2y", "trading_cost_pct": 0.002},
    )

    assert response.status_code == 200
    assert seen == {"period": "2y", "trading_cost_pct": 0.002}


def test_post_backtest_defaults_to_five_years(monkeypatch):
    seen = {}

    def fake_get_price_data(symbol, period):
        seen["period"] = period
        return _price_frame([100.0])

    monkeypatch.setattr(backtest_route, "get_price_data", fake_get_price_data)

    response = client.post("/backtest", json={"symbol": "aapl"})

    assert response.status_code == 200
    assert seen == {"period": "5y"}


def test_post_backtest_rejects_unknown_period():
    response = client.post("/backtest", json={"symbol": "aapl", "period": "3d"})

    assert response.status_code == 422


def test_post_backtest_rejects_negative_trading_cost():
    response = client.post("/backtest", json={"symbol": "aapl", "trading_cost_pct": -0.01})

    assert response.status_code == 422
