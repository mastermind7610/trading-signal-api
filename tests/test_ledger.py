import random

import pandas as pd
import pytest

from pipeline.ledger import AccountState, apply_day
from services import backtest as backtest_service
from services.backtest import run_backtest
from services.decisions import make_decision
from services.features import build_features
from services.signal import REQUIRED_FEATURE_COLUMNS, generate_signal_from_features

STARTING_EQUITY = 10_000.0


def _random_walk(length=400, start=100.0, seed=0):
    # Deterministic noisy prices where the open gaps away from the previous
    # close, so the overnight and open-to-close legs both carry real moves.
    rng = random.Random(seed)
    rows = []
    close = start
    for _ in range(length):
        open_price = close * (1 + rng.gauss(0.0, 0.004))
        close = open_price * (1 + rng.gauss(0.0005, 0.015))
        rows.append((round(open_price, 2), round(close, 2)))
    opens, closes = zip(*rows, strict=True)
    return pd.DataFrame({"Open": list(opens), "Close": list(closes)})


def _replay(price_data, trading_cost_pct):
    """Trade a whole history one day at a time through apply_day.

    Signals come from the real strategy functions, called the way the daily
    pipeline will call them: one day's signal sets the target that fills at
    the next day's open.
    """
    features = build_features(price_data)
    tradeable = features[REQUIRED_FEATURE_COLUMNS].notna().all(axis=1).to_numpy()
    start = int(tradeable.argmax())
    opens = price_data["Open"].to_numpy()
    closes = price_data["Close"].to_numpy()

    state = AccountState(equity=STARTING_EQUITY)
    days = []
    for index in range(start, len(features) - 1):
        signal = generate_signal_from_features(
            "TEST", features.iloc[index : index + 1], log_decision=False
        )
        target = make_decision(signal["signal"], signal["confidence"], 1.0)["position_pct"]
        day = apply_day(
            state,
            prev_close=closes[index],
            open_price=opens[index + 1],
            close_price=closes[index + 1],
            target_pct=target,
            trading_cost_pct=trading_cost_pct,
        )
        days.append(day)
        state = day.state
    return days


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
@pytest.mark.parametrize("trading_cost_pct", [0.0, 0.001, 0.01])
def test_day_by_day_ledger_matches_run_backtest(seed, trading_cost_pct):
    price_data = _random_walk(seed=seed)

    expected = run_backtest("TEST", price_data, trading_cost_pct=trading_cost_pct)
    days = _replay(price_data, trading_cost_pct)

    returns = pd.Series([day.daily_return for day in days])
    cumulative_return = days[-1].equity / STARTING_EQUITY - 1

    signal_days = (
        expected["buy_signals"] + expected["sell_signals"] + expected["hold_signals"]
    )
    assert len(days) == signal_days
    assert round(cumulative_return, 4) == expected["cumulative_strategy_return"]
    assert backtest_service._annualized_sharpe(returns) == expected["sharpe_ratio"]
    assert backtest_service._max_drawdown(returns) == expected["max_drawdown"]
    assert sum(day.traded for day in days) == expected["trades"]
    assert round(sum(day.cost_pct for day in days), 6) == expected["total_trading_costs"]
    assert (
        round(sum(day.position_after for day in days) / len(days), 4)
        == expected["average_exposure"]
    )


def test_replayed_histories_actually_trade():
    # Guards the comparison above against passing on all-cash histories.
    for seed in [0, 1, 2, 3]:
        days = _replay(_random_walk(seed=seed), 0.001)
        assert sum(day.traded for day in days) > 0
        assert any(day.position_after > 0 for day in days)


def test_cash_account_with_no_target_does_not_move():
    day = apply_day(
        AccountState(equity=STARTING_EQUITY),
        prev_close=100.0,
        open_price=103.0,
        close_price=95.0,
        target_pct=0.0,
    )

    assert day.daily_return == 0.0
    assert day.cost_pct == 0.0
    assert day.traded is False
    assert day.equity == STARTING_EQUITY
    assert day.position_value == 0.0
    assert day.cash == STARTING_EQUITY


def test_buy_fills_at_the_open_and_pays_cost_on_the_amount_traded():
    # 10% bought at the open of 100, close 110: +10% on a tenth of the
    # account is +1%, less 0.1% cost on the 10% traded (0.01%).
    day = apply_day(
        AccountState(equity=STARTING_EQUITY),
        prev_close=90.0,  # the overnight gap is missed: nothing was held
        open_price=100.0,
        close_price=110.0,
        target_pct=0.10,
        trading_cost_pct=0.001,
    )

    assert day.position_before == 0.0
    assert day.position_after == 0.10
    assert day.traded is True
    assert day.traded_pct == pytest.approx(0.10)
    assert day.cost_pct == pytest.approx(0.0001)
    assert day.daily_return == pytest.approx(0.0099)
    assert day.equity == pytest.approx(10_099.0)
    assert day.position_value == pytest.approx(1_009.90)
    assert day.cash == pytest.approx(9_089.10)


def test_old_position_is_held_overnight_before_the_sell_fills():
    # 10% held from 100 to an open of 105 earns +0.5%, then it is sold:
    # the fall to 50 by the close is not suffered, and the sale costs 0.01%.
    day = apply_day(
        AccountState(equity=STARTING_EQUITY, position_pct=0.10),
        prev_close=100.0,
        open_price=105.0,
        close_price=50.0,
        target_pct=0.0,
        trading_cost_pct=0.001,
    )

    assert day.daily_return == pytest.approx(0.005 - 0.0001)
    assert day.position_after == 0.0
    assert day.cash == pytest.approx(day.equity)


def test_unchanged_position_pays_no_cost():
    day = apply_day(
        AccountState(equity=STARTING_EQUITY, position_pct=0.05),
        prev_close=100.0,
        open_price=100.0,
        close_price=102.0,
        target_pct=0.05,
        trading_cost_pct=0.001,
    )

    assert day.traded is False
    assert day.cost_pct == 0.0
    assert day.daily_return == pytest.approx(0.05 * 0.02)


def test_state_carries_the_closing_account_into_the_next_day():
    day = apply_day(
        AccountState(equity=STARTING_EQUITY),
        prev_close=100.0,
        open_price=100.0,
        close_price=101.0,
        target_pct=0.08,
    )

    assert day.state == AccountState(equity=day.equity, position_pct=0.08)


@pytest.mark.parametrize(
    "overrides",
    [
        {"prev_close": 0.0},
        {"open_price": -1.0},
        {"close_price": float("nan")},
        {"target_pct": -0.01},
        {"target_pct": 1.01},
        {"trading_cost_pct": -0.001},
    ],
)
def test_apply_day_rejects_invalid_input(overrides):
    arguments = {
        "prev_close": 100.0,
        "open_price": 100.0,
        "close_price": 100.0,
        "target_pct": 0.05,
        "trading_cost_pct": 0.001,
    }
    arguments.update(overrides)

    with pytest.raises(ValueError):
        apply_day(AccountState(equity=STARTING_EQUITY), **arguments)
