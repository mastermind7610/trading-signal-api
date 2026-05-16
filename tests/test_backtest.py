import pandas as pd
import pytest

from services.backtest import run_backtest


def _price_data(close_prices):
    return pd.DataFrame({"Close": close_prices})


def test_run_backtest_counts_buy_signals():
    result = run_backtest("aapl", _price_data(list(range(100, 161))))

    assert result["symbol"] == "AAPL"
    assert result["buy_signals"] > 0
    assert result["sell_signals"] == 0
    assert result["hold_signals"] > 0
    assert result["cumulative_strategy_return"] > 0
    assert result["buy_and_hold_return"] > 0


def test_run_backtest_counts_sell_signals():
    result = run_backtest("msft", _price_data(list(range(160, 99, -1))))

    assert result["symbol"] == "MSFT"
    assert result["buy_signals"] == 0
    assert result["sell_signals"] > 0
    assert result["hold_signals"] > 0
    assert result["cumulative_strategy_return"] > 0
    assert result["buy_and_hold_return"] < 0


def test_run_backtest_counts_hold_signals_for_flat_prices():
    result = run_backtest("spy", _price_data([100.0] * 61))

    assert result == {
        "symbol": "SPY",
        "buy_signals": 0,
        "sell_signals": 0,
        "hold_signals": 60,
        "cumulative_strategy_return": 0.0,
        "buy_and_hold_return": 0.0,
    }


def test_run_backtest_handles_insufficient_data():
    result = run_backtest("tsla", _price_data([100.0]))

    assert result == {
        "symbol": "TSLA",
        "buy_signals": 0,
        "sell_signals": 0,
        "hold_signals": 0,
        "cumulative_strategy_return": 0.0,
        "buy_and_hold_return": 0.0,
    }


def test_run_backtest_requires_close_column():
    with pytest.raises(ValueError, match="Close column is required"):
        run_backtest("nvda", pd.DataFrame({"Open": [100.0, 101.0]}))
