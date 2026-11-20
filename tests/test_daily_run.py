import pandas as pd
import pytest

from ledger_samples import (
    DAY_AFTER_HOLIDAY,
    DAY_BEFORE_HOLIDAY,
    HOLIDAY,
    bar_dates,
    bars_through,
    sample_prices,
)
from pipeline.daily import DEFAULT_STARTING_EQUITY, LedgerGapError, run_daily
from pipeline.repository import InMemoryLedgerRepository
from services import backtest as backtest_service
from services.backtest import run_backtest
from services.signal import REQUIRED_FEATURE_COLUMNS


def test_first_run_opens_the_account_on_the_latest_bar():
    price_data = sample_prices()
    repository = InMemoryLedgerRepository()

    recorded = run_daily(" test ", price_data, repository, starting_equity=5_000.0)

    assert len(recorded) == 1
    assert repository.history("TEST") == recorded

    entry = recorded[0]
    dates = bar_dates(price_data)
    assert entry.symbol == "TEST"
    assert entry.trade_date == dates[-1]
    assert entry.signal_date == dates[-2]
    assert entry.prev_close == price_data["Close"].iloc[-2]
    assert entry.open_price == price_data["Open"].iloc[-1]
    assert entry.close_price == price_data["Close"].iloc[-1]
    # The account starts in cash with the starting equity.
    assert entry.day.position_before == 0.0
    assert entry.day.equity == pytest.approx(5_000.0 * (1 + entry.day.daily_return))


def test_running_twice_on_the_same_prices_records_the_day_once():
    price_data = sample_prices()
    repository = InMemoryLedgerRepository()

    first = run_daily("TEST", price_data, repository)
    second = run_daily("TEST", price_data, repository)
    third = run_daily("TEST", price_data, repository)

    assert len(first) == 1
    assert second == []
    assert third == []
    assert repository.history("TEST") == first


def test_rerun_after_several_days_changes_nothing():
    price_data = sample_prices()
    repository = InMemoryLedgerRepository()
    for day in bar_dates(price_data)[-5:]:
        run_daily("TEST", bars_through(price_data, day), repository)
    before = repository.history("TEST")

    assert run_daily("TEST", price_data, repository) == []
    assert repository.history("TEST") == before
    assert len(before) == 5


def test_run_on_a_holiday_records_nothing():
    price_data = sample_prices()
    assert HOLIDAY not in bar_dates(price_data)
    repository = InMemoryLedgerRepository()

    run_daily("TEST", bars_through(price_data, DAY_BEFORE_HOLIDAY), repository)
    before = repository.history("TEST")

    # On the holiday the newest bar is still the day before's.
    recorded = run_daily("TEST", bars_through(price_data, HOLIDAY), repository)

    assert recorded == []
    assert repository.history("TEST") == before
    assert repository.latest("TEST").trade_date == DAY_BEFORE_HOLIDAY


def test_day_after_a_holiday_follows_on_from_the_day_before_it():
    price_data = sample_prices()
    repository = InMemoryLedgerRepository()
    run_daily("TEST", bars_through(price_data, DAY_BEFORE_HOLIDAY), repository)
    run_daily("TEST", bars_through(price_data, HOLIDAY), repository)

    recorded = run_daily("TEST", bars_through(price_data, DAY_AFTER_HOLIDAY), repository)

    assert [entry.trade_date for entry in recorded] == [DAY_AFTER_HOLIDAY]
    entry = recorded[0]
    assert entry.signal_date == DAY_BEFORE_HOLIDAY
    assert entry.prev_close == price_data["Close"][pd.Timestamp(DAY_BEFORE_HOLIDAY)]
    assert [e.trade_date for e in repository.history("TEST")] == [
        DAY_BEFORE_HOLIDAY,
        DAY_AFTER_HOLIDAY,
    ]


@pytest.mark.parametrize("missed", [1, 3, 10])
def test_catch_up_after_missed_days_matches_running_every_day(missed):
    price_data = sample_prices()
    dates = bar_dates(price_data)
    window = dates[-(missed + 2) :]

    every_day = InMemoryLedgerRepository()
    for day in window:
        run_daily("TEST", bars_through(price_data, day), every_day)

    # Runs on the first day, misses `missed` days, then runs on the last.
    caught_up = InMemoryLedgerRepository()
    run_daily("TEST", bars_through(price_data, window[0]), caught_up)
    recorded = run_daily("TEST", bars_through(price_data, window[-1]), caught_up)

    assert [entry.trade_date for entry in recorded] == window[1:]
    assert caught_up.history("TEST") == every_day.history("TEST")
    # The missed days were not idle: the position changed during them.
    assert any(entry.day.traded for entry in recorded)


def test_catch_up_carries_the_account_from_one_day_to_the_next():
    price_data = sample_prices()
    repository = InMemoryLedgerRepository()
    run_daily("TEST", bars_through(price_data, bar_dates(price_data)[-8]), repository)
    run_daily("TEST", price_data, repository)

    history = repository.history("TEST")
    assert len(history) == 8
    assert any(entry.day.position_after > 0 for entry in history)
    assert history[-1].day.equity != DEFAULT_STARTING_EQUITY
    for previous, entry in zip(history, history[1:], strict=False):
        assert entry.signal_date == previous.trade_date
        assert entry.prev_close == previous.close_price
        assert entry.day.position_before == previous.day.position_after
        assert entry.day.equity == pytest.approx(
            previous.day.equity * (1 + entry.day.daily_return)
        )


@pytest.mark.parametrize("seed", [0, 1])
def test_daily_runs_over_a_whole_history_match_run_backtest(seed):
    price_data = sample_prices(length=300, seed=seed)
    expected = run_backtest("TEST", price_data)

    # Start the account on the backtest's first traded day, then run daily.
    features_ready = (
        backtest_service.build_features(price_data)[REQUIRED_FEATURE_COLUMNS]
        .notna()
        .all(axis=1)
        .to_numpy()
    )
    start = int(features_ready.argmax())
    repository = InMemoryLedgerRepository()
    for day in bar_dates(price_data)[start + 1 :]:
        run_daily("TEST", bars_through(price_data, day), repository)

    history = repository.history("TEST")
    returns = pd.Series([entry.day.daily_return for entry in history])
    signals = [entry.signal for entry in history]

    assert expected["trades"] > 0
    assert signals.count("BUY") == expected["buy_signals"]
    assert signals.count("SELL") == expected["sell_signals"]
    assert signals.count("HOLD") == expected["hold_signals"]
    assert (
        round(history[-1].day.equity / DEFAULT_STARTING_EQUITY - 1, 4)
        == expected["cumulative_strategy_return"]
    )
    assert backtest_service._annualized_sharpe(returns) == expected["sharpe_ratio"]
    assert backtest_service._max_drawdown(returns) == expected["max_drawdown"]
    assert sum(entry.day.traded for entry in history) == expected["trades"]


def test_ledger_older_than_the_price_data_is_refused_not_skipped():
    price_data = sample_prices()
    repository = InMemoryLedgerRepository()
    run_daily("TEST", bars_through(price_data, bar_dates(price_data)[-10]), repository)
    before = repository.history("TEST")

    # The table no longer reaches back to the last recorded day.
    with pytest.raises(LedgerGapError):
        run_daily("TEST", price_data.iloc[-5:], repository)

    assert repository.history("TEST") == before


def test_price_data_older_than_the_ledger_records_nothing():
    price_data = sample_prices()
    repository = InMemoryLedgerRepository()
    run_daily("TEST", price_data, repository)

    assert run_daily("TEST", price_data.iloc[:-3], repository) == []
    assert len(repository.history("TEST")) == 1


def test_failed_catch_up_records_none_of_the_missed_days():
    price_data = sample_prices()
    dates = bar_dates(price_data)
    repository = InMemoryLedgerRepository()
    run_daily("TEST", bars_through(price_data, dates[-6]), repository)
    before = repository.history("TEST")

    broken = price_data.copy()
    broken.loc[pd.Timestamp(dates[-2]), "Open"] = 0.0

    with pytest.raises(ValueError):
        run_daily("TEST", broken, repository)

    assert repository.history("TEST") == before


def test_bars_without_a_price_are_ignored_like_the_backtest_does():
    price_data = sample_prices()
    dates = bar_dates(price_data)
    with_gap = price_data.copy()
    with_gap.loc[pd.Timestamp(dates[-1]), "Close"] = float("nan")
    repository = InMemoryLedgerRepository()

    recorded = run_daily("TEST", with_gap, repository)

    assert [entry.trade_date for entry in recorded] == [dates[-2]]


def test_thin_history_holds_cash():
    price_data = sample_prices().iloc[-10:]
    repository = InMemoryLedgerRepository()

    recorded = run_daily("TEST", price_data, repository)

    assert len(recorded) == 1
    assert recorded[0].signal == "HOLD"
    assert recorded[0].reason == "insufficient_feature_data"
    assert recorded[0].day.equity == DEFAULT_STARTING_EQUITY


def test_single_bar_records_nothing():
    repository = InMemoryLedgerRepository()

    assert run_daily("TEST", sample_prices().iloc[-1:], repository) == []
    assert repository.history("TEST") == []


def test_symbols_have_separate_accounts():
    repository = InMemoryLedgerRepository()

    run_daily("AAA", sample_prices(seed=1), repository)
    run_daily("BBB", sample_prices(seed=2), repository)

    assert len(repository.history("AAA")) == 1
    assert len(repository.history("BBB")) == 1
    assert run_daily("AAA", sample_prices(seed=1), repository) == []


@pytest.mark.parametrize(
    "price_data",
    [
        sample_prices().drop(columns=["Open"]),
        sample_prices().reset_index(drop=True),
        sample_prices().iloc[::-1],
    ],
    ids=["no_open_column", "not_indexed_by_date", "newest_first"],
)
def test_run_daily_rejects_malformed_price_data(price_data):
    with pytest.raises(ValueError):
        run_daily("TEST", price_data, InMemoryLedgerRepository())


@pytest.mark.parametrize(
    "arguments",
    [
        {"symbol": "  "},
        {"starting_equity": 0.0},
        {"starting_equity": float("nan")},
        {"trading_cost_pct": -0.001},
    ],
)
def test_run_daily_rejects_invalid_arguments(arguments):
    call = {"symbol": "TEST", **arguments}
    symbol = call.pop("symbol")

    with pytest.raises(ValueError):
        run_daily(symbol, sample_prices(), InMemoryLedgerRepository(), **call)
