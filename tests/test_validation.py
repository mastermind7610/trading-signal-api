import pandas as pd
import pytest
from fastapi.testclient import TestClient

from main import app
from routes import backtest as backtest_route
from routes import signal as signal_route

client = TestClient(app)


@pytest.fixture
def signal_calls(monkeypatch):
    """Replace the signal service so only request validation is exercised.

    Returns the list of (symbol, portfolio_value) pairs the route passed on.
    """
    calls = []

    def fake_generate_signal(symbol, portfolio_value=10000):
        calls.append((symbol, portfolio_value))
        return {
            "symbol": symbol,
            "signal": "HOLD",
            "confidence": 0.5,
            "reason": "no_ma_crossover",
            "decision": {"position_pct": 0.0, "position_value": 0.0},
        }

    monkeypatch.setattr(signal_route, "generate_signal", fake_generate_signal)
    return calls


@pytest.fixture
def backtest_calls(monkeypatch):
    """Replace the data fetch so only request validation is exercised.

    A one-row frame makes the real backtest return its empty result.
    """
    calls = []

    def fake_get_price_data(symbol, period):
        calls.append(symbol)
        return pd.DataFrame({"Open": [100.0], "Close": [100.0]})

    monkeypatch.setattr(backtest_route, "get_price_data", fake_get_price_data)
    return calls


# ----------------------------------------------------------------- /signal


def test_signal_symbol_is_trimmed_and_uppercased(signal_calls):
    response = client.post("/signal", json={"symbol": "  aapl "})

    assert response.status_code == 200
    assert response.json()["symbol"] == "AAPL"
    assert signal_calls == [("AAPL", 10000)]


@pytest.mark.parametrize("symbol", ["BRK-B", "BRK.B", "^GSPC", "EURUSD=X", "ES=F", "BTC-USD"])
def test_signal_accepts_yahoo_ticker_syntax(signal_calls, symbol):
    response = client.post("/signal", json={"symbol": symbol})

    assert response.status_code == 200
    assert signal_calls == [(symbol, 10000)]


@pytest.mark.parametrize("symbol", ["", "   ", "AA PL", "AAPL;DROP", "aapl!", "A" * 13])
def test_signal_rejects_malformed_symbol(signal_calls, symbol):
    response = client.post("/signal", json={"symbol": symbol})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "symbol"]
    assert signal_calls == []


def test_signal_requires_symbol(signal_calls):
    response = client.post("/signal", json={})

    assert response.status_code == 422
    assert signal_calls == []


@pytest.mark.parametrize("portfolio_value", [0, -1, -10000, 1_000_000_001])
def test_signal_rejects_non_positive_or_oversized_portfolio(signal_calls, portfolio_value):
    response = client.post(
        "/signal", json={"symbol": "AAPL", "portfolio_value": portfolio_value}
    )

    assert response.status_code == 422
    assert signal_calls == []


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_signal_rejects_non_finite_portfolio(signal_calls, literal):
    # Python's JSON parser accepts these non-standard literals, so the schema
    # has to reject them explicitly rather than rely on the parser. The error
    # body echoes the input, which the app must render as text or the 422
    # itself fails to serialize.
    response = client.post(
        "/signal",
        content=f'{{"symbol": "AAPL", "portfolio_value": {literal}}}',
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["loc"] == ["body", "portfolio_value"]
    assert error["msg"] == "Input should be a finite number"
    assert signal_calls == []


def test_signal_portfolio_value_defaults_to_10000(signal_calls):
    response = client.post("/signal", json={"symbol": "AAPL"})

    assert response.status_code == 200
    assert signal_calls == [("AAPL", 10000)]


def test_signal_accepts_smallest_positive_portfolio(signal_calls):
    response = client.post("/signal", json={"symbol": "AAPL", "portfolio_value": 1})

    assert response.status_code == 200
    assert signal_calls == [("AAPL", 1)]


# --------------------------------------------------------------- /backtest


def test_backtest_symbol_is_trimmed_and_uppercased(backtest_calls):
    response = client.post("/backtest", json={"symbol": " msft "})

    assert response.status_code == 200
    assert response.json()["symbol"] == "MSFT"
    assert backtest_calls == ["MSFT"]


@pytest.mark.parametrize("symbol", ["", "AAPL;DROP", "A" * 13])
def test_backtest_rejects_malformed_symbol(backtest_calls, symbol):
    response = client.post("/backtest", json={"symbol": symbol})

    assert response.status_code == 422
    assert backtest_calls == []
