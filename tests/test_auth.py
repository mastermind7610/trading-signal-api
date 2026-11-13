import pandas as pd
import pytest
from fastapi.testclient import TestClient

from main import app
from routes import backtest as backtest_route
from routes import signal as signal_route
from routes.auth import API_KEY_ENV_VAR

# Every test here runs with the API key check exactly as deployed.
pytestmark = pytest.mark.real_auth

client = TestClient(app)

# Not real credentials: arbitrary strings that exist only inside these tests.
TEST_KEY = "test-key-one"
SECOND_TEST_KEY = "test-key-two"


@pytest.fixture
def signal_service_stub(monkeypatch):
    """Keep the signal route off the network; record whether it was reached."""
    calls = []

    def fake_generate_signal(symbol, portfolio_value=10000):
        calls.append(symbol)
        return {
            "symbol": symbol,
            "signal": "HOLD",
            "confidence": 0.5,
            "decision": {"position_pct": 0.0, "position_value": 0.0},
        }

    monkeypatch.setattr(signal_route, "generate_signal", fake_generate_signal)
    return calls


def test_signal_without_key_is_401(monkeypatch, signal_service_stub):
    monkeypatch.setenv(API_KEY_ENV_VAR, TEST_KEY)

    response = client.post("/signal", json={"symbol": "AAPL"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Missing or invalid API key."}
    assert response.headers["www-authenticate"] == "ApiKey"
    assert signal_service_stub == []


@pytest.mark.parametrize("wrong", ["", "nope", TEST_KEY + "x", TEST_KEY[:-1], TEST_KEY.upper()])
def test_signal_with_wrong_key_is_401(monkeypatch, signal_service_stub, wrong):
    monkeypatch.setenv(API_KEY_ENV_VAR, TEST_KEY)

    response = client.post("/signal", json={"symbol": "AAPL"}, headers={"X-API-Key": wrong})

    assert response.status_code == 401
    assert signal_service_stub == []


def test_signal_with_correct_key_is_200(monkeypatch, signal_service_stub):
    monkeypatch.setenv(API_KEY_ENV_VAR, TEST_KEY)

    response = client.post("/signal", json={"symbol": "AAPL"}, headers={"X-API-Key": TEST_KEY})

    assert response.status_code == 200
    assert signal_service_stub == ["AAPL"]


@pytest.mark.parametrize("key", [TEST_KEY, SECOND_TEST_KEY])
def test_any_key_in_a_comma_separated_list_is_accepted(monkeypatch, signal_service_stub, key):
    # Two keys at once is what makes rotation possible without downtime.
    monkeypatch.setenv(API_KEY_ENV_VAR, f"{TEST_KEY}, {SECOND_TEST_KEY}")

    response = client.post("/signal", json={"symbol": "AAPL"}, headers={"X-API-Key": key})

    assert response.status_code == 200


@pytest.mark.parametrize("configured", [None, "", "  ", ","])
def test_unconfigured_server_fails_closed(monkeypatch, signal_service_stub, configured):
    if configured is None:
        monkeypatch.delenv(API_KEY_ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(API_KEY_ENV_VAR, configured)

    response = client.post("/signal", json={"symbol": "AAPL"}, headers={"X-API-Key": "anything"})

    assert response.status_code == 503
    assert API_KEY_ENV_VAR in response.json()["detail"]
    assert signal_service_stub == []


def test_backtest_is_protected_too(monkeypatch):
    monkeypatch.setenv(API_KEY_ENV_VAR, TEST_KEY)
    fetched = []

    def fake_get_price_data(symbol, period):
        fetched.append(symbol)
        return pd.DataFrame({"Open": [100.0], "Close": [100.0]})

    monkeypatch.setattr(backtest_route, "get_price_data", fake_get_price_data)

    denied = client.post("/backtest", json={"symbol": "AAPL"})
    allowed = client.post("/backtest", json={"symbol": "AAPL"}, headers={"X-API-Key": TEST_KEY})

    assert denied.status_code == 401
    assert allowed.status_code == 200
    assert fetched == ["AAPL"]


@pytest.mark.parametrize("path", ["/health", "/docs", "/openapi.json"])
def test_health_and_docs_stay_public(monkeypatch, path):
    # Even on a server with no key configured.
    monkeypatch.delenv(API_KEY_ENV_VAR, raising=False)

    response = client.get(path)

    assert response.status_code == 200


def test_openapi_declares_the_api_key_scheme():
    schema = client.get("/openapi.json").json()

    schemes = schema["components"]["securitySchemes"]
    assert {"type": "apiKey", "in": "header", "name": "X-API-Key"}.items() <= next(
        iter(schemes.values())
    ).items()
    assert schema["paths"]["/signal"]["post"]["security"]
    assert schema["paths"]["/backtest"]["post"]["security"]
    assert "security" not in schema["paths"]["/health"]["get"]
