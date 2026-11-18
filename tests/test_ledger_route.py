"""GET /ledger/{symbol}: reading the paper-trading ledger (no database)."""

from dataclasses import asdict
from datetime import date

import pytest
from fastapi.testclient import TestClient

from ledger_samples import sample_entry
from main import RETRY_AFTER_SECONDS, app
from pipeline.mongo_repository import (
    LEDGER_COLLECTION,
    MONGODB_URI_ENV_VAR,
    UNAVAILABLE_MESSAGE,
    MongoLedgerRepository,
)
from pipeline.repository import InMemoryLedgerRepository, LedgerStorageError
from routes import ledger as ledger_route

client = TestClient(app)


@pytest.fixture(autouse=True)
def _no_cached_client():
    # Tests that set MONGODB_URI must not see a client built by another test.
    ledger_route._repository_for.cache_clear()
    yield
    ledger_route._repository_for.cache_clear()


def _serve(repository):
    app.dependency_overrides[ledger_route.get_ledger_repository] = lambda: repository


@pytest.fixture
def repository():
    """An in-memory ledger served in place of MongoDB."""
    repository = InMemoryLedgerRepository()
    _serve(repository)
    yield repository
    app.dependency_overrides.pop(ledger_route.get_ledger_repository, None)


class _UnavailableRepository:
    """A ledger whose database cannot be reached."""

    def __init__(self):
        self.reads = []

    def history(self, symbol):
        self.reads.append(symbol)
        raise LedgerStorageError(UNAVAILABLE_MESSAGE)


def test_returns_every_recorded_day_oldest_first(repository):
    for day in (date(2026, 11, 12), date(2026, 11, 13), date(2026, 11, 16)):
        repository.append(sample_entry("AAPL", day))
    repository.append(sample_entry("MSFT", date(2026, 11, 13)))

    response = client.get("/ledger/AAPL")

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "AAPL"
    assert [entry["trade_date"] for entry in body["entries"]] == [
        "2026-11-12",
        "2026-11-13",
        "2026-11-16",
    ]


def test_reports_each_entry_exactly(repository):
    entry = sample_entry("AAPL", date(2026, 11, 13))
    repository.append(entry)

    response = client.get("/ledger/AAPL")

    # Exact equality: the response must not round the account's figures.
    assert response.json()["entries"] == [
        {
            "trade_date": "2026-11-13",
            "signal_date": "2026-11-12",
            "signal": entry.signal,
            "confidence": entry.confidence,
            "reason": entry.reason,
            "prev_close": entry.prev_close,
            "open_price": entry.open_price,
            "close_price": entry.close_price,
            **asdict(entry.day),
        }
    ]


@pytest.mark.parametrize("path", ["/ledger/aapl", "/ledger/%20aapl%20"])
def test_symbol_is_trimmed_and_upper_cased(repository, path):
    repository.append(sample_entry("AAPL", date(2026, 11, 13)))

    response = client.get(path)

    assert response.status_code == 200
    assert response.json()["symbol"] == "AAPL"


def test_symbol_with_no_ledger_is_404(repository):
    repository.append(sample_entry("AAPL", date(2026, 11, 13)))

    response = client.get("/ledger/msft")

    assert response.status_code == 404
    assert response.json() == {"detail": "No ledger found for symbol: MSFT"}


@pytest.mark.parametrize("symbol", ["AAPL!", "A" * 13, "%20%20%20", "AA%20PL"])
def test_invalid_symbol_is_422(repository, symbol):
    response = client.get(f"/ledger/{symbol}")

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["path", "symbol"]


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_ledger_cannot_be_written_through_the_api(repository, method):
    repository.append(sample_entry("AAPL", date(2026, 11, 13)))

    response = getattr(client, method)("/ledger/AAPL")

    assert response.status_code == 405
    assert len(repository.history("AAPL")) == 1


def test_unreachable_database_is_503_with_retry_after():
    unavailable = _UnavailableRepository()
    _serve(unavailable)
    try:
        response = client.get("/ledger/AAPL")
    finally:
        app.dependency_overrides.pop(ledger_route.get_ledger_repository, None)

    assert response.status_code == 503
    assert response.json() == {"detail": UNAVAILABLE_MESSAGE}
    assert response.headers["retry-after"] == str(RETRY_AFTER_SECONDS)
    assert unavailable.reads == ["AAPL"]


@pytest.mark.parametrize("configured", [None, "", "   "])
def test_unconfigured_ledger_is_503(monkeypatch, configured):
    if configured is None:
        monkeypatch.delenv(MONGODB_URI_ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(MONGODB_URI_ENV_VAR, configured)

    response = client.get("/ledger/AAPL")

    assert response.status_code == 503
    assert MONGODB_URI_ENV_VAR in response.json()["detail"]


def test_malformed_connection_string_is_503_and_not_repeated(monkeypatch):
    # Not a real credential: an arbitrary string that exists only in this test.
    monkeypatch.setenv(MONGODB_URI_ENV_VAR, "notmongo://reader:hunter2@db.example.invalid")

    response = client.get("/ledger/AAPL")

    assert response.status_code == 503
    assert response.json() == {
        "detail": f"{MONGODB_URI_ENV_VAR} is not a valid MongoDB connection string."
    }
    assert "hunter2" not in response.text
    assert "db.example" not in response.text


def test_one_client_serves_every_request(monkeypatch):
    # connect=False in ledger_repository_from_uri: building the repository
    # opens no connection, so this needs no database.
    monkeypatch.setenv(MONGODB_URI_ENV_VAR, "mongodb://db.example.invalid:27017/paper")

    first = ledger_route.get_ledger_repository()
    second = ledger_route.get_ledger_repository()

    try:
        assert isinstance(first, MongoLedgerRepository)
        assert second is first
        assert first.collection.database.name == "paper"
        assert first.collection.name == LEDGER_COLLECTION
    finally:
        first.collection.database.client.close()
