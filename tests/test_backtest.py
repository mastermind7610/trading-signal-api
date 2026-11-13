import math
import random

import pandas as pd
import pytest

from services import backtest as backtest_service
from services.backtest import run_backtest
from services.features import build_features
from services.signal import REQUIRED_FEATURE_COLUMNS

# With flat prices, rows 0-53 are indicator warm-up and row 54 is the first
# day a signal can be computed.
FIRST_SIGNAL_ROW = 54


def _price_data(close_prices):
    # Open equal to Close is enough for tests that only check signal counts.
    return pd.DataFrame({"Open": close_prices, "Close": close_prices})


def _open_close(rows):
    opens, closes = zip(*rows)
    return pd.DataFrame({"Open": list(opens), "Close": list(closes)})


def _warmup_rows():
    # Flat rows up to and including the first signal day.
    return [(100.0, 100.0)] * (FIRST_SIGNAL_ROW + 1)


def _script_signals(monkeypatch, script):
    """Replace the strategy with fixed (signal, confidence) pairs, one per day.

    Days past the end of the script are HOLD.
    """
    days = iter(script)

    def fake_signal(symbol, features, log_decision=True):
        signal, confidence = next(days, ("HOLD", 0.5))
        return {"symbol": symbol, "signal": signal, "confidence": confidence}

    monkeypatch.setattr(backtest_service, "generate_signal_from_features", fake_signal)


def _rising_series(length=90, start=100.0):
    # Net-upward sawtooth (+2 / -1) keeps RSI moderate so the overbought
    # override does not suppress every BUY, as a monotonic series would.
    prices = []
    value = start
    for i in range(length):
        value += 2 if i % 2 == 0 else -1
        prices.append(value)
    return prices


def _falling_series(length=90, start=250.0):
    # Net-downward sawtooth (-2 / +1) keeps RSI moderate so the oversold
    # override does not suppress every SELL.
    prices = []
    value = start
    for i in range(length):
        value += -2 if i % 2 == 0 else 1
        prices.append(value)
    return prices


def test_run_backtest_counts_buy_signals():
    result = run_backtest("aapl", _price_data(_rising_series()))

    assert result["symbol"] == "AAPL"
    assert result["buy_signals"] > 0
    assert result["sell_signals"] == 0
    assert result["hold_signals"] > 0
    assert result["buy_and_hold_return"] > 0
    # The MACD momentum filter downgrades BUYs whenever the histogram turns
    # negative, which whipsaws this naive crossover strategy on a mean-reverting
    # sawtooth. We no longer assert the strategy is profitable here, only that
    # the metrics are computed.
    assert math.isfinite(result["cumulative_strategy_return"])
    assert math.isfinite(result["sharpe_ratio"])
    # Position size follows confidence, so BUY days put real money to work.
    assert result["average_exposure"] > 0


def _random_walk(length=260, start=100.0, seed=0):
    # Deterministic noisy series with realistic daily moves, so both signal
    # directions and the overrides all get exercised.
    rng = random.Random(seed)
    prices = []
    value = start
    for _ in range(length):
        value *= 1 + rng.gauss(0.0005, 0.015)
        prices.append(round(value, 2))
    return prices


def test_run_backtest_evaluates_each_day_from_its_own_row(monkeypatch):
    # The engine hands the signal function one row per day instead of the
    # whole history so far. That must not change a single signal: from the
    # first tradeable row on, every row has all required features, so the
    # "latest complete row" of the full history is that same row.
    price_data = _price_data(_random_walk())
    real = backtest_service.generate_signal_from_features
    seen = []

    def recording(symbol, features, log_decision=True):
        result = real(symbol, features, log_decision=log_decision)
        seen.append((len(features), result))
        return result

    monkeypatch.setattr(backtest_service, "generate_signal_from_features", recording)

    result = run_backtest("aapl", price_data)

    features = build_features(price_data)
    tradeable = features[REQUIRED_FEATURE_COLUMNS].notna().all(axis=1).to_numpy()
    start = int(tradeable.argmax())
    expected = [
        real("AAPL", features.iloc[: index + 1], log_decision=False)
        for index in range(start, len(features) - 1)
    ]

    assert all(rows == 1 for rows, _ in seen)
    assert [signal for _, signal in seen] == expected
    assert len({signal["signal"] for signal in expected}) >= 2
    assert result["buy_signals"] + result["sell_signals"] + result["hold_signals"] == len(expected)


def test_run_backtest_counts_sell_signals():
    result = run_backtest("msft", _price_data(_falling_series()))

    assert result["symbol"] == "MSFT"
    assert result["buy_signals"] == 0
    assert result["sell_signals"] > 0
    assert result["hold_signals"] > 0
    assert result["buy_and_hold_return"] < 0
    # Long-only: SELL means cash, so with no BUYs the strategy never holds
    # stock and neither gains nor loses.
    assert result["average_exposure"] == 0.0
    assert result["trades"] == 0
    assert result["cumulative_strategy_return"] == 0.0


def test_run_backtest_counts_hold_signals_for_flat_prices():
    result = run_backtest("spy", _price_data([100.0] * 61))

    # Rows 0-53 are feature warm-up, so only rows 54-59 produce signals.
    assert result == {
        "symbol": "SPY",
        "buy_signals": 0,
        "sell_signals": 0,
        "hold_signals": 6,
        "cumulative_strategy_return": 0.0,
        "buy_and_hold_return": 0.0,
        "sharpe_ratio": 0.0,
        "max_drawdown": 0.0,
        "trades": 0,
        "total_trading_costs": 0.0,
        "average_exposure": 0.0,
    }


def test_run_backtest_buy_and_hold_excludes_warmup():
    # Price doubles during the 54-row warm-up, when no signal is possible,
    # then stays flat. Buy-and-hold must be measured over the same flat days
    # the strategy trades, not credited with the warm-up gain.
    prices = [100.0 + i for i in range(54)] + [200.0] * 20
    result = run_backtest("aapl", _price_data(prices), trading_cost_pct=0.0)

    assert result["buy_and_hold_return"] == 0.0
    assert result["cumulative_strategy_return"] == 0.0
    assert result["buy_signals"] + result["sell_signals"] + result["hold_signals"] == 19


def test_run_backtest_handles_insufficient_data():
    result = run_backtest("tsla", _price_data([100.0]))

    assert result == {
        "symbol": "TSLA",
        "buy_signals": 0,
        "sell_signals": 0,
        "hold_signals": 0,
        "cumulative_strategy_return": 0.0,
        "buy_and_hold_return": 0.0,
        "sharpe_ratio": 0.0,
        "max_drawdown": 0.0,
        "trades": 0,
        "total_trading_costs": 0.0,
        "average_exposure": 0.0,
    }


@pytest.mark.parametrize("columns", [{"Open": [100.0, 101.0]}, {"Close": [100.0, 101.0]}])
def test_run_backtest_requires_open_and_close_columns(columns):
    with pytest.raises(ValueError, match="Open and Close columns are required"):
        run_backtest("nvda", pd.DataFrame(columns))


def test_run_backtest_rejects_negative_trading_cost():
    with pytest.raises(ValueError, match="cannot be negative"):
        run_backtest("nvda", _price_data([100.0] * 61), trading_cost_pct=-0.001)


# Rows after warm-up for the fill tests: a +10% gap at the next open, a +10%
# move during that day, then another +10% gap the morning after.
_GAP_ROWS = [(110.0, 121.0), (133.1, 133.1), (133.1, 133.1)]


def test_run_backtest_fills_at_next_open(monkeypatch):
    # BUY at max confidence (10% position) on the first signal day only.
    _script_signals(monkeypatch, [("BUY", 0.95)])
    prices = _open_close(_warmup_rows() + _GAP_ROWS)

    result = run_backtest("aapl", prices, trading_cost_pct=0.0)

    # The order fills at the next open (110), so the overnight gap from 100
    # is missed. The 10% position earns the +10% day (+1%), is sold at the
    # following open after another +10% gap (+1%), then sits in cash.
    assert result["cumulative_strategy_return"] == pytest.approx(1.01 * 1.01 - 1, abs=1e-4)
    assert result["trades"] == 2
    assert result["average_exposure"] == pytest.approx(0.1 / 3, abs=1e-4)
    assert result["buy_and_hold_return"] == pytest.approx(0.331, abs=1e-4)


def test_run_backtest_charges_trading_costs(monkeypatch):
    _script_signals(monkeypatch, [("BUY", 0.95)])
    prices = _open_close(_warmup_rows() + _GAP_ROWS)

    result = run_backtest("aapl", prices, trading_cost_pct=0.01)

    # Buying and then selling a 10% position each cost 0.1 x 1% = 0.1%.
    assert result["total_trading_costs"] == pytest.approx(0.002)
    assert result["cumulative_strategy_return"] == pytest.approx(1.009 * 1.009 - 1, abs=1e-4)


def test_run_backtest_sizes_positions_like_signal_endpoint(monkeypatch):
    # Confidence 0.725 sits halfway through the [0.5, 0.95] range, so
    # make_decision sizes the position at half the 10% maximum.
    _script_signals(monkeypatch, [("BUY", 0.725)] * 10)
    prices = _open_close(_warmup_rows() + [(100.0, 100.0)] * 5)

    result = run_backtest("aapl", prices)

    assert result["average_exposure"] == pytest.approx(0.05)
    # Held at the same size every day, so only the first purchase is a trade.
    assert result["trades"] == 1
    assert result["total_trading_costs"] == pytest.approx(0.05 * 0.001)


def test_run_backtest_reports_max_drawdown(monkeypatch):
    _script_signals(monkeypatch, [("BUY", 0.95)] * 10)
    # Price halves, then recovers. A 10% position loses 5%, then gains 10%.
    prices = _open_close(_warmup_rows() + [(100.0, 100.0), (50.0, 50.0), (100.0, 100.0)])

    result = run_backtest("aapl", prices, trading_cost_pct=0.0)

    assert result["max_drawdown"] == pytest.approx(-0.05)
    assert result["cumulative_strategy_return"] == pytest.approx(0.95 * 1.1 - 1, abs=1e-4)
