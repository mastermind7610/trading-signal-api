"""The daily run's command line: which bars it uses, what it reports, and
its exit status. Prices and the ledger are supplied in memory; nothing here
reaches Yahoo Finance or MongoDB."""

import runpy
import sys
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from ledger_samples import bar_dates, sample_prices
from pipeline import cli
from pipeline.cli import (
    EXIT_FAILED,
    EXIT_OK,
    EXIT_USAGE,
    HISTORY_PERIOD,
    completed_bars,
    main,
    run,
    update_ledger,
)
from pipeline.mongo_repository import MONGODB_URI_ENV_VAR
from pipeline.repository import InMemoryLedgerRepository, LedgerStorageError
from services.data import MarketDataUnavailableError, NoPriceDataError

NEW_YORK = "America/New_York"
LAST_DAY = date(2026, 12, 4)
DAY_BEFORE_LAST = date(2026, 12, 3)

# Moments around the last sample bar, Friday 2026-12-04 (New York is UTC-5).
DURING_LAST_SESSION = datetime(2026, 12, 4, 17, 0, tzinfo=UTC)  # 12:00 in New York
AFTER_LAST_CLOSE = datetime(2026, 12, 4, 21, 30, tzinfo=UTC)  # 16:30 in New York
BEFORE_MIDNIGHT_NEW_YORK = datetime(2026, 12, 5, 4, 59, tzinfo=UTC)  # 23:59 on the 4th
AFTER_MIDNIGHT_NEW_YORK = datetime(2026, 12, 5, 5, 0, tzinfo=UTC)  # 00:00 on the 5th


def _market_prices(timezone=NEW_YORK, **kwargs):
    """Sample bars indexed the way Yahoo Finance returns them: midnight in
    the exchange's timezone."""
    return sample_prices(**kwargs).tz_localize(timezone)


def _fetcher(frames):
    """A stand-in for get_price_data serving the given frame per symbol,
    recording each call."""
    calls = []

    def fetch_prices(symbol, period):
        calls.append((symbol, period))
        result = frames[symbol]
        if isinstance(result, Exception):
            raise result
        return result

    fetch_prices.calls = calls
    return fetch_prices


# --- which bars are complete ------------------------------------------------


@pytest.mark.parametrize(
    ("now", "last_bar_used"),
    [
        (DURING_LAST_SESSION, DAY_BEFORE_LAST),
        (AFTER_LAST_CLOSE, DAY_BEFORE_LAST),
        (BEFORE_MIDNIGHT_NEW_YORK, DAY_BEFORE_LAST),
        (AFTER_MIDNIGHT_NEW_YORK, LAST_DAY),
    ],
    ids=["market_open", "after_close", "before_midnight", "after_midnight"],
)
def test_a_bar_is_used_once_its_date_is_over_in_the_exchange_timezone(now, last_bar_used):
    price_data = _market_prices()

    completed = completed_bars(price_data, now)

    assert bar_dates(completed)[-1] == last_bar_used
    # Only the newest bar is ever in question.
    assert len(completed) >= len(price_data) - 1


def test_the_exchange_timezone_decides_not_the_callers():
    # 15:00 UTC on the 4th is already the 5th in Tokyo, where the bar for
    # the 4th is finished, and still mid-session on the 4th in New York.
    now = datetime(2026, 12, 4, 15, 0, tzinfo=UTC)

    tokyo = completed_bars(_market_prices("Asia/Tokyo"), now)
    new_york = completed_bars(_market_prices(NEW_YORK), now)

    assert bar_dates(tokyo)[-1] == LAST_DAY
    assert bar_dates(new_york)[-1] == DAY_BEFORE_LAST


@pytest.mark.parametrize(
    ("now", "last_bar_used"),
    [
        (datetime(2026, 12, 4, 23, 59, tzinfo=UTC), DAY_BEFORE_LAST),
        (datetime(2026, 12, 5, 0, 0, tzinfo=UTC), LAST_DAY),
    ],
)
def test_dates_without_a_timezone_are_compared_with_the_utc_date(now, last_bar_used):
    completed = completed_bars(sample_prices(), now)

    assert bar_dates(completed)[-1] == last_bar_used


def test_now_is_converted_from_whatever_timezone_it_is_given_in():
    # The same instant as AFTER_MIDNIGHT_NEW_YORK, written as Tokyo time.
    now = pd.Timestamp("2026-12-05 14:00", tz="Asia/Tokyo").to_pydatetime()

    assert bar_dates(completed_bars(_market_prices(), now))[-1] == LAST_DAY


def test_a_table_without_dates_is_left_for_the_daily_run_to_reject():
    undated = sample_prices().reset_index(drop=True)

    assert completed_bars(undated, AFTER_MIDNIGHT_NEW_YORK) is undated
    with pytest.raises(ValueError, match="indexed by date"):
        update_ledger(
            "TEST", InMemoryLedgerRepository(), _fetcher({"TEST": undated}), AFTER_LAST_CLOSE
        )


# --- one symbol -------------------------------------------------------------


def test_update_fetches_two_years_and_records_only_completed_days():
    fetch_prices = _fetcher({"TEST": _market_prices()})
    repository = InMemoryLedgerRepository()

    recorded = update_ledger("TEST", repository, fetch_prices, DURING_LAST_SESSION)

    assert fetch_prices.calls == [("TEST", HISTORY_PERIOD)]
    assert HISTORY_PERIOD == "2y"
    assert [entry.trade_date for entry in recorded] == [DAY_BEFORE_LAST]
    assert repository.latest("TEST").trade_date == DAY_BEFORE_LAST


def test_a_day_is_recorded_with_its_final_close_not_a_price_from_mid_session():
    final = _market_prices()
    final_close = final["Close"].iloc[-1]
    mid_session = final.copy()
    mid_session.iloc[-1, mid_session.columns.get_loc("Close")] = final_close * 1.07
    repository = InMemoryLedgerRepository()

    # A run while the market is open sees the unfinished bar and leaves it.
    update_ledger("TEST", repository, _fetcher({"TEST": mid_session}), DURING_LAST_SESSION)
    assert repository.latest("TEST").trade_date == DAY_BEFORE_LAST

    # The next run after the day is over records it, from the finished bar.
    recorded = update_ledger("TEST", repository, _fetcher({"TEST": final}), AFTER_MIDNIGHT_NEW_YORK)

    assert [entry.trade_date for entry in recorded] == [LAST_DAY]
    assert recorded[0].close_price == final_close


# --- the whole run ----------------------------------------------------------


def test_run_reports_each_recorded_day_and_exits_zero(capsys):
    fetch_prices = _fetcher({"AAA": _market_prices(seed=2), "BBB": _market_prices(seed=3)})
    repository = InMemoryLedgerRepository()

    status = run(["AAA", "BBB"], repository, fetch_prices, AFTER_MIDNIGHT_NEW_YORK)

    output = capsys.readouterr()
    assert status == EXIT_OK
    assert output.err == ""
    lines = output.out.splitlines()
    assert len(lines) == 2
    entry = repository.latest("AAA")
    assert lines[0] == (
        f"AAA 2026-12-04: {entry.signal} ({entry.reason}), "
        f"position {entry.day.position_after:.2%}, "
        f"return {entry.day.daily_return:+.4%}, equity {entry.day.equity:,.2f}"
    )
    assert lines[1].startswith("BBB 2026-12-04: ")


def test_second_run_records_nothing_and_says_the_ledger_is_up_to_date(capsys):
    fetch_prices = _fetcher({"AAA": _market_prices()})
    repository = InMemoryLedgerRepository()
    run(["AAA"], repository, fetch_prices, AFTER_MIDNIGHT_NEW_YORK)
    before = repository.history("AAA")
    capsys.readouterr()

    status = run(["AAA"], repository, fetch_prices, AFTER_MIDNIGHT_NEW_YORK)

    assert status == EXIT_OK
    assert capsys.readouterr().out == "AAA: up to date, last recorded day 2026-12-04\n"
    assert repository.history("AAA") == before


def test_run_after_missed_days_reports_every_day_it_catches_up(capsys):
    price_data = _market_prices()
    repository = InMemoryLedgerRepository()
    run(["AAA"], repository, _fetcher({"AAA": price_data.iloc[:-3]}), AFTER_MIDNIGHT_NEW_YORK)
    capsys.readouterr()

    status = run(["AAA"], repository, _fetcher({"AAA": price_data}), AFTER_MIDNIGHT_NEW_YORK)

    lines = capsys.readouterr().out.splitlines()
    assert status == EXIT_OK
    assert [line.split(":")[0] for line in lines] == [
        "AAA 2026-12-02",
        "AAA 2026-12-03",
        "AAA 2026-12-04",
    ]


def test_symbol_with_too_little_history_has_nothing_to_record(capsys):
    fetch_prices = _fetcher({"NEW": _market_prices().iloc[-1:]})

    status = run(["NEW"], InMemoryLedgerRepository(), fetch_prices, AFTER_MIDNIGHT_NEW_YORK)

    assert status == EXIT_OK
    assert capsys.readouterr().out == "NEW: nothing to record yet\n"


@pytest.mark.parametrize(
    "error",
    [
        NoPriceDataError("No price data found for symbol: BAD"),
        MarketDataUnavailableError("Market data for BAD is temporarily unavailable."),
    ],
)
def test_a_failed_symbol_is_reported_and_the_others_still_run(capsys, error):
    fetch_prices = _fetcher(
        {"AAA": _market_prices(seed=2), "BAD": error, "CCC": _market_prices(seed=3)}
    )
    repository = InMemoryLedgerRepository()

    status = run(["AAA", "BAD", "CCC"], repository, fetch_prices, AFTER_MIDNIGHT_NEW_YORK)

    output = capsys.readouterr()
    assert status == EXIT_FAILED
    assert output.err == f"BAD: failed: {error}\n"
    assert len(repository.history("AAA")) == 1
    assert len(repository.history("CCC")) == 1
    assert repository.history("BAD") == []


def test_a_storage_failure_is_reported_and_exits_nonzero(capsys):
    class UnreachableRepository(InMemoryLedgerRepository):
        def latest(self, symbol):
            raise LedgerStorageError("The ledger database is unavailable. Try again shortly.")

    status = run(
        ["AAA"], UnreachableRepository(), _fetcher({"AAA": _market_prices()}), AFTER_LAST_CLOSE
    )

    output = capsys.readouterr()
    assert status == EXIT_FAILED
    assert output.out == ""
    assert output.err == "AAA: failed: The ledger database is unavailable. Try again shortly.\n"


def test_prices_that_do_not_reach_back_to_the_ledger_fail_without_recording(capsys):
    price_data = _market_prices()
    repository = InMemoryLedgerRepository()
    run(["AAA"], repository, _fetcher({"AAA": price_data.iloc[:-10]}), AFTER_MIDNIGHT_NEW_YORK)
    capsys.readouterr()

    status = run(
        ["AAA"], repository, _fetcher({"AAA": price_data.iloc[-5:]}), AFTER_MIDNIGHT_NEW_YORK
    )

    assert status == EXIT_FAILED
    assert "AAA: failed: The AAA ledger ends on" in capsys.readouterr().err
    assert len(repository.history("AAA")) == 1


# --- the command line -------------------------------------------------------


@pytest.fixture
def wired(monkeypatch):
    """main() with an in-memory ledger and sample prices behind it.

    Returns the repository main() will be given, with the connection strings
    it was asked to open in `.uris` and the price fetches in `.fetches`. The
    sample bars end on 2026-12-04, so tests pass main() a `now` after that.
    """
    repository = InMemoryLedgerRepository()
    repository.uris = []
    repository.fetches = []

    def fake_repository_from_uri(uri):
        repository.uris.append(uri)
        return repository

    def fake_get_price_data(symbol, period):
        repository.fetches.append(symbol)
        return _market_prices()

    monkeypatch.setattr(cli, "ledger_repository_from_uri", fake_repository_from_uri)
    monkeypatch.setattr(cli, "get_price_data", fake_get_price_data)
    monkeypatch.setenv(MONGODB_URI_ENV_VAR, "mongodb://ledger.example/paper")
    return repository


def test_main_runs_each_symbol_once_upper_cased_against_the_configured_database(wired, capsys):
    status = main([" spy", "SPY", "aapl"], now=AFTER_MIDNIGHT_NEW_YORK)

    assert status == EXIT_OK
    assert wired.uris == ["mongodb://ledger.example/paper"]
    assert wired.fetches == ["SPY", "AAPL"]
    assert wired.latest("SPY").trade_date == LAST_DAY
    assert wired.latest("AAPL").trade_date == LAST_DAY
    assert len(capsys.readouterr().out.splitlines()) == 2


def test_main_judges_the_newest_bar_by_the_time_it_is_given(wired):
    main(["SPY"], now=DURING_LAST_SESSION)

    assert wired.latest("SPY").trade_date == DAY_BEFORE_LAST


@pytest.mark.parametrize(
    ("last_bar", "recorded_days"),
    [("2020-01-10", [date(2020, 1, 10)]), ("2100-01-08", [])],
    ids=["bars_long_past", "bars_far_in_the_future"],
)
def test_main_uses_the_current_time_unless_told_otherwise(
    wired, monkeypatch, last_bar, recorded_days
):
    # Whenever this test runs, 2020 is over and 2100 has not begun.
    monkeypatch.setattr(
        cli, "get_price_data", lambda symbol, period: _market_prices(end=last_bar)
    )

    main(["SPY"])

    assert [entry.trade_date for entry in wired.history("SPY")] == recorded_days


@pytest.mark.parametrize("value", [None, "", "  "])
def test_main_without_a_connection_string_exits_2_and_fetches_nothing(
    wired, monkeypatch, capsys, value
):
    if value is None:
        monkeypatch.delenv(MONGODB_URI_ENV_VAR)
    else:
        monkeypatch.setenv(MONGODB_URI_ENV_VAR, value)

    status = main(["SPY"], now=AFTER_MIDNIGHT_NEW_YORK)

    assert status == EXIT_USAGE
    assert MONGODB_URI_ENV_VAR in capsys.readouterr().err
    assert wired.uris == []
    assert wired.fetches == []


def test_main_with_a_malformed_connection_string_exits_2_without_repeating_it(
    monkeypatch, capsys
):
    fetches = []
    monkeypatch.setattr(cli, "get_price_data", lambda symbol, period: fetches.append(symbol))
    monkeypatch.setenv(MONGODB_URI_ENV_VAR, "mongodb://user:not-a-real-password@host:notaport")

    status = main(["SPY"])

    output = capsys.readouterr()
    assert status == EXIT_USAGE
    assert output.err == f"{MONGODB_URI_ENV_VAR} is not a valid MongoDB connection string.\n"
    assert "not-a-real-password" not in output.out + output.err
    assert fetches == []


@pytest.mark.parametrize("arguments", [[], ["SPY", "  "]])
def test_main_requires_symbols(wired, capsys, arguments):
    with pytest.raises(SystemExit) as excinfo:
        main(arguments)

    assert excinfo.value.code == EXIT_USAGE
    assert "usage: python -m pipeline" in capsys.readouterr().err
    assert wired.fetches == []


def test_main_returns_the_failure_status_of_the_run(wired, monkeypatch, capsys):
    def no_data(symbol, period):
        raise NoPriceDataError(f"No price data found for symbol: {symbol}")

    monkeypatch.setattr(cli, "get_price_data", no_data)

    assert main(["SPY"]) == EXIT_FAILED
    assert capsys.readouterr().err == "SPY: failed: No price data found for symbol: SPY\n"


def test_python_dash_m_pipeline_runs_main(monkeypatch, capsys):
    monkeypatch.delenv(MONGODB_URI_ENV_VAR, raising=False)
    monkeypatch.setattr(sys, "argv", ["pipeline", "SPY"])

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("pipeline", run_name="__main__")

    assert excinfo.value.code == EXIT_USAGE
    assert MONGODB_URI_ENV_VAR in capsys.readouterr().err
