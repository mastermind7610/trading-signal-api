import pandas as pd

from services.features import build_features
from services.signal import generate_signal_from_features


SIGNALS = ("BUY", "SELL", "HOLD")
SIGNAL_EXPOSURE = {
    "BUY": 1,
    "SELL": -1,
    "HOLD": 0,
}

# Trading days per year, used to annualize the Sharpe ratio.
TRADING_DAYS_PER_YEAR = 252
# Risk-free rate assumed when computing the Sharpe ratio.
RISK_FREE_RATE = 0.0


def _annualized_sharpe(returns: pd.Series) -> float:
    """Annualized Sharpe ratio of daily returns, assuming a 0.0 risk-free rate.

    Returns 0.0 when the ratio is undefined (too few points or zero variance).
    """
    excess_returns = returns - RISK_FREE_RATE
    std = excess_returns.std()

    if len(excess_returns) < 2 or pd.isna(std) or std == 0:
        return 0.0

    sharpe = (excess_returns.mean() / std) * (TRADING_DAYS_PER_YEAR ** 0.5)
    return float(round(sharpe, 4))


def run_backtest(symbol: str, price_data: pd.DataFrame) -> dict:
    cleaned_symbol = symbol.strip().upper()

    if "Close" not in price_data.columns:
        raise ValueError("Close column is required for backtesting.")

    clean_prices = price_data.dropna(subset=["Close"]).copy()

    if len(clean_prices) < 2:
        return {
            "symbol": cleaned_symbol,
            "buy_signals": 0,
            "sell_signals": 0,
            "hold_signals": 0,
            "cumulative_strategy_return": 0.0,
            "buy_and_hold_return": 0.0,
            "sharpe_ratio": 0.0,
        }

    features = build_features(clean_prices)
    signal_counts = {signal: 0 for signal in SIGNALS}
    strategy_returns = []

    for index in range(len(features) - 1):
        feature_window = features.iloc[: index + 1]
        signal_result = generate_signal_from_features(
            cleaned_symbol,
            feature_window,
            log_decision=False,
        )
        signal = signal_result["signal"]
        signal_counts[signal] += 1

        current_close = clean_prices["Close"].iloc[index]
        next_close = clean_prices["Close"].iloc[index + 1]
        market_return = (next_close / current_close) - 1
        strategy_returns.append(market_return * SIGNAL_EXPOSURE[signal])

    strategy_returns_series = pd.Series(strategy_returns)
    cumulative_strategy_return = (strategy_returns_series + 1).prod() - 1
    buy_and_hold_return = (clean_prices["Close"].iloc[-1] / clean_prices["Close"].iloc[0]) - 1

    return {
        "symbol": cleaned_symbol,
        "buy_signals": signal_counts["BUY"],
        "sell_signals": signal_counts["SELL"],
        "hold_signals": signal_counts["HOLD"],
        "cumulative_strategy_return": float(round(cumulative_strategy_return, 4)),
        "buy_and_hold_return": float(round(buy_and_hold_return, 4)),
        "sharpe_ratio": _annualized_sharpe(strategy_returns_series),
    }