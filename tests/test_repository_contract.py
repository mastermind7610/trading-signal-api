"""What every LedgerRepository must do, run against each implementation.

The in-memory repository is always tested. The MongoDB one is tested when
MONGODB_URI is set and skipped when it is not. Each MongoDB test gets its
own collection with a random name, dropped afterwards, so these tests never
read or write the real ledger collection.
"""

import uuid
from datetime import date

import pytest
from pymongo.errors import DuplicateKeyError

from ledger_samples import bar_dates, bars_through, sample_entry, sample_prices
from pipeline.daily import run_daily
from pipeline.mongo_repository import (
    MONGODB_URI_ENV_VAR,
    configured_mongodb_uri,
    entry_to_document,
    ledger_repository_from_uri,
)
from pipeline.repository import InMemoryLedgerRepository, OutOfOrderEntryError


@pytest.fixture
def mongo_repository():
    uri = configured_mongodb_uri()
    if uri is None:
        pytest.skip(f"{MONGODB_URI_ENV_VAR} is not set")

    repository = ledger_repository_from_uri(
        uri, collection_name=f"ledger_test_{uuid.uuid4().hex}"
    )
    yield repository
    repository.collection.drop()
    repository.collection.database.client.close()


@pytest.fixture(params=["memory", "mongo"])
def repository(request):
    if request.param == "memory":
        return InMemoryLedgerRepository()
    return request.getfixturevalue("mongo_repository")


def test_empty_repository_has_no_latest_entry_and_no_history(repository):
    assert repository.latest("TEST") is None
    assert repository.history("TEST") == []


def test_entries_come_back_exactly_as_recorded(repository):
    entry = sample_entry("TEST", date(2026, 11, 3))

    repository.append(entry)

    # Dataclass equality: every date, flag and float is the same value.
    assert repository.latest("TEST") == entry
    assert repository.history("TEST") == [entry]


def test_history_is_oldest_first_and_latest_is_the_newest(repository):
    days = [date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 30), date(2026, 12, 1)]
    entries = [sample_entry("TEST", day) for day in days]

    for entry in entries:
        repository.append(entry)

    assert repository.history("TEST") == entries
    assert repository.latest("TEST") == entries[-1]


@pytest.mark.parametrize("trade_date", [date(2026, 11, 3), date(2026, 11, 2)])
def test_an_entry_that_is_not_later_than_the_latest_is_rejected(repository, trade_date):
    recorded = sample_entry("TEST", date(2026, 11, 3))
    repository.append(recorded)

    with pytest.raises(OutOfOrderEntryError):
        repository.append(sample_entry("TEST", trade_date))

    assert repository.history("TEST") == [recorded]


def test_each_symbol_has_its_own_history(repository):
    repository.append(sample_entry("AAA", date(2026, 11, 3)))
    # Earlier than AAA's latest day, which only matters within one symbol.
    repository.append(sample_entry("BBB", date(2026, 11, 2)))

    assert [entry.symbol for entry in repository.history("AAA")] == ["AAA"]
    assert repository.latest("BBB").trade_date == date(2026, 11, 2)
    assert repository.latest("CCC") is None


def test_editing_the_returned_history_does_not_change_the_ledger(repository):
    repository.append(sample_entry("TEST", date(2026, 11, 3)))

    repository.history("TEST").clear()

    assert len(repository.history("TEST")) == 1


def test_daily_run_through_the_repository_matches_the_in_memory_ledger(repository):
    # The run as a whole, on real signals and prices: first day, a rerun, and
    # a catch-up over missed days must leave the same ledger in any store.
    price_data = sample_prices()
    dates = bar_dates(price_data)
    reference = InMemoryLedgerRepository()

    for store in (repository, reference):
        run_daily("TEST", bars_through(price_data, dates[-12]), store)
        assert run_daily("TEST", bars_through(price_data, dates[-12]), store) == []
        run_daily("TEST", price_data, store)

    history = repository.history("TEST")
    assert len(history) == 12
    assert history == reference.history("TEST")
    assert any(entry.day.traded for entry in history)
    assert run_daily("TEST", price_data, repository) == []


# --- MongoDB only -----------------------------------------------------------


def test_mongo_unique_index_refuses_a_second_entry_for_the_same_day(mongo_repository):
    entry = sample_entry("TEST", date(2026, 11, 3))
    mongo_repository.append(entry)

    # Written straight to the collection, as a second run that had not seen
    # the first one's entry would: the database itself must refuse it.
    with pytest.raises(DuplicateKeyError):
        mongo_repository.collection.insert_one(entry_to_document(entry))

    assert mongo_repository.history("TEST") == [entry]


def test_mongo_reads_need_no_index_and_create_none(mongo_repository):
    assert mongo_repository.history("TEST") == []
    assert mongo_repository.latest("TEST") is None

    assert mongo_repository.collection.name not in (
        mongo_repository.collection.database.list_collection_names()
    )
