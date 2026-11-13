from fastapi.testclient import TestClient

from main import API_VERSION, app

client = TestClient(app)


def _openapi():
    response = client.get("/openapi.json")
    assert response.status_code == 200
    return response.json()


def test_health_reports_status_and_version():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": API_VERSION}


def test_openapi_info_describes_the_service():
    info = _openapi()["info"]

    assert info["title"] == "TRADING_SIMMS"
    assert info["version"] == API_VERSION
    assert "places no" in info["description"]


def test_openapi_routes_are_tagged():
    paths = _openapi()["paths"]

    assert paths["/signal"]["post"]["tags"] == ["signals"]
    assert paths["/backtest"]["post"]["tags"] == ["backtests"]
    assert paths["/health"]["get"]["tags"] == ["health"]


def test_openapi_documents_error_responses():
    schema = _openapi()

    for path in ("/signal", "/backtest"):
        responses = schema["paths"][path]["post"]["responses"]
        for status in ("200", "401", "404", "422", "503"):
            assert status in responses, (path, status)
        error_ref = responses["404"]["content"]["application/json"]["schema"]["$ref"]
        assert error_ref.endswith("/ErrorResponse")


def test_openapi_models_carry_examples():
    schemas = _openapi()["components"]["schemas"]

    for name in ("SignalRequest", "SignalResponse", "BacktestRequest", "BacktestResponse"):
        assert schemas[name]["examples"], name
    assert schemas["SignalRequest"]["examples"][0]["symbol"] == "AAPL"
