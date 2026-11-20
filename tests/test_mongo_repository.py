"""The parts of the MongoDB repository that can be tested without a database.

How entries become documents, how the connection string is read, and what
the repository does when the driver raises. Its behaviour against a real
database is in tests/test_repository_contract.py, which needs MONGODB_URI.
"""

from datetime import date

import bson
import pytest
from pymongo.errors import DuplicateKeyError, ServerSelectionTimeoutError

from ledger_samples import sample_entry, sample_prices
from pipeline import mongo_repository
from pipeline.daily import run_daily
from pipeline.mongo_repository import (
    DEFAULT_DATABASE,
    LEDGER_COLLECTION,
    MONGODB_URI_ENV_VAR,
    OPERATION_TIMEOUT_MS,
    MongoLedgerRepository,
    configured_mongodb_uri,
    entry_from_document,
    entry_to_document,
    ledger_repository_from_uri,
)
from pipeline.repository import (
    InMemoryLedgerRepository,
    LedgerStorageError,
    OutOfOrderEntryError,
)

# Not a real credential: it exists only to check that it is never repeated.
FAKE_PASSWORD = "not-a-real-password"


class FakeCollection:
    """Stands in for a pymongo collection: holds no data, records the calls
    that matter here, and raises `error` from every operation if it is set."""

    def __init__(self, error=None, insert_error=None):
        self.error = error
        self.insert_error = insert_error
        self.created_indexes = []
        self.inserted = []

    def _fail_if_asked(self):
        if self.error is not None:
            raise self.error

    def find_one(self, query, sort=None):
        self._fail_if_asked()
        return None

    def find(self, query):
        self._fail_if_asked()
        return self

    def sort(self, key, direction):
        return iter(())

    def create_index(self, keys, unique=False):
        self._fail_if_asked()
        self.created_indexes.append((keys, unique))

    def insert_one(self, document):
        self._fail_if_asked()
        if self.insert_error is not None:
            raise self.insert_error
        self.inserted.append(document)


def _real_entries():
    """Entries produced by the daily run, with the floats real prices give."""
    price_data = sample_prices()
    repository = InMemoryLedgerRepository()
    run_daily("TEST", price_data.iloc[:-10], repository)
    run_daily("TEST", price_data, repository)
    history = repository.history("TEST")
    assert any(entry.day.traded for entry in history)
    return history


# --- entries as documents ---------------------------------------------------


def test_document_survives_bson_encoding_unchanged():
    # bson is the encoding the driver sends to the server, so this is the
    # round trip an entry makes through the database, minus the network.
    for entry in _real_entries():
        stored = bson.decode(bson.encode(entry_to_document(entry)))

        assert entry_from_document(stored) == entry


def test_document_holds_dates_as_iso_strings_and_the_day_as_a_sub_document():
    entry = sample_entry("TEST", date(2026, 11, 3))

    document = entry_to_document(entry)

    assert document["symbol"] == "TEST"
    assert document["trade_date"] == "2026-11-03"
    assert document["signal_date"] == "2026-11-02"
    assert document["signal"] == "BUY"
    assert document["day"]["position_after"] == 0.0733
    assert document["day"]["traded"] is True
    assert document["day"]["equity"] == entry.day.equity
    assert set(document) == {
        "symbol",
        "trade_date",
        "signal_date",
        "signal",
        "confidence",
        "reason",
        "prev_close",
        "open_price",
        "close_price",
        "day",
    }


def test_iso_date_strings_sort_in_date_order():
    days = [date(2026, 12, 1), date(2025, 12, 31), date(2026, 2, 10), date(2026, 11, 30)]

    as_stored = [entry_to_document(sample_entry("TEST", day))["trade_date"] for day in days]

    assert sorted(as_stored) == [day.isoformat() for day in sorted(days)]


def test_the_id_mongodb_adds_is_ignored_when_reading():
    entry = sample_entry("TEST", date(2026, 11, 3))
    stored = {"_id": bson.ObjectId(), **entry_to_document(entry)}

    assert entry_from_document(stored) == entry


# --- the connection string --------------------------------------------------


@pytest.mark.parametrize("value", [None, "", "   "])
def test_connection_string_is_none_when_unset_or_blank(monkeypatch, value):
    if value is None:
        monkeypatch.delenv(MONGODB_URI_ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(MONGODB_URI_ENV_VAR, value)

    assert configured_mongodb_uri() is None


def test_connection_string_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv(MONGODB_URI_ENV_VAR, "  mongodb://localhost:27017  ")

    assert configured_mongodb_uri() == "mongodb://localhost:27017"


@pytest.mark.parametrize(
    ("uri", "database"),
    [
        ("mongodb://localhost:27017/paper", "paper"),
        ("mongodb://localhost:27017", DEFAULT_DATABASE),
        ("mongodb://localhost:27017/?retryWrites=true", DEFAULT_DATABASE),
    ],
)
def test_repository_uses_the_database_named_in_the_connection_string(uri, database):
    # Building the repository opens no connection, so no server is needed.
    repository = ledger_repository_from_uri(uri)
    client = repository.collection.database.client

    assert repository.collection.database.name == database
    assert repository.collection.name == LEDGER_COLLECTION
    assert client.options.timeout == OPERATION_TIMEOUT_MS / 1000
    client.close()


@pytest.mark.parametrize(
    "uri",
    [
        f"mongodb://user:{FAKE_PASSWORD}/more@host/db",
        f"mongodb://user:{FAKE_PASSWORD}@host:notaport/db",
        f"https://user:{FAKE_PASSWORD}@host/db",
        "mongodb://",
    ],
)
def test_malformed_connection_string_is_refused_without_repeating_it(uri):
    with pytest.raises(LedgerStorageError) as excinfo:
        ledger_repository_from_uri(uri)

    assert MONGODB_URI_ENV_VAR in str(excinfo.value)
    assert FAKE_PASSWORD not in str(excinfo.value)
    # The driver's own error can quote the string, so it is not chained.
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__ is True


# --- the repository when the driver raises ----------------------------------


def _unreachable():
    return ServerSelectionTimeoutError("cluster0-shard-00-00.example.net:27017: timed out")


@pytest.mark.parametrize(
    "operation",
    [
        lambda repository: repository.latest("TEST"),
        lambda repository: repository.history("TEST"),
        lambda repository: repository.append(sample_entry("TEST", date(2026, 11, 3))),
    ],
    ids=["latest", "history", "append"],
)
def test_unreachable_database_is_reported_as_a_storage_error(operation, caplog):
    repository = MongoLedgerRepository(FakeCollection(error=_unreachable()))

    with caplog.at_level("WARNING", logger=mongo_repository.__name__):
        with pytest.raises(LedgerStorageError) as excinfo:
            operation(repository)

    # The caller gets a plain message; the driver's detail goes to the log.
    assert str(excinfo.value) == mongo_repository.UNAVAILABLE_MESSAGE
    assert "example.net" not in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, ServerSelectionTimeoutError)
    assert "ServerSelectionTimeoutError" in caplog.text
    assert "example.net" in caplog.text


def test_failed_insert_is_reported_as_a_storage_error():
    collection = FakeCollection(insert_error=_unreachable())
    repository = MongoLedgerRepository(collection)

    with pytest.raises(LedgerStorageError):
        repository.append(sample_entry("TEST", date(2026, 11, 3)))

    assert collection.inserted == []


def test_duplicate_key_from_the_database_is_an_out_of_order_entry():
    # Two overlapping runs: this one's check found nothing, then the other
    # run's insert landed first and the unique index refused this one.
    collection = FakeCollection(insert_error=DuplicateKeyError("E11000 duplicate key"))
    repository = MongoLedgerRepository(collection)

    with pytest.raises(OutOfOrderEntryError, match="2026-11-03"):
        repository.append(sample_entry("TEST", date(2026, 11, 3)))


def test_first_write_creates_the_unique_index_and_later_writes_do_not():
    collection = FakeCollection()
    repository = MongoLedgerRepository(collection)

    repository.latest("TEST")
    repository.history("TEST")
    assert collection.created_indexes == []

    repository.append(sample_entry("TEST", date(2026, 11, 3)))
    repository.append(sample_entry("TEST", date(2026, 11, 4)))

    assert collection.created_indexes == [([("symbol", 1), ("trade_date", 1)], True)]
    assert [document["trade_date"] for document in collection.inserted] == [
        "2026-11-03",
        "2026-11-04",
    ]
