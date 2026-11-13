import pandas as pd

from services.decisions import make_decision
from services.features import build_features
from services.signal import REQUIRED_FEATURE_COLUMNS, generate_signal_from_features


SIGNALS = ("BUY", "SELL", "HOLD")

# Trading days per year, used to annualize the Sharpe ratio.
TRADING_DAYS_PER_YEAR = 252
# Risk-free rate assumed when computing the Sharpe ratio.
RISK_FREE_RATE = 0.0
# Default cost of trading (commission plus slippage), as a fraction of the
# amount bought or sold. 0.001 = 0.1%.
DEFAULT_TRADING_COST_PCT = 0.001


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


def _max_drawdown(returns: pd.Series) -> float:
    """Largest peak-to-trough fall in portfolio value, as a negative decimal."""
    equity = (returns + 1).cumprod()
    # Portfolio starts at 1.0, so the peak is never below that.
    peak = equity.cummax().clip(lower=1.0)
    return float(round((equity / peak - 1).min(), 4))


def _empty_result(symbol: str) -> dict:
    return {
        "symbol": symbol,
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


def run_backtest(
    symbol: str,
    price_data: pd.DataFrame,
    trading_cost_pct: float = DEFAULT_TRADING_COST_PCT,
) -> dict:
    """Walk-forward, long-only backtest that trades the way /signal advises.

    Each day's signal uses data up to that day's close. The resulting order
    fills at the next day's open, sized with the same rule /signal uses
    (0-10% of the portfolio on BUY, cash on SELL or HOLD). Every change in
    position pays trading_cost_pct on the amount traded.
    """
    cleaned_symbol = symbol.strip().upper()

    if "Open" not in price_data.columns or "Close" not in price_data.columns:
        raise ValueError("Open and Close columns are required for backtesting.")

    if trading_cost_pct < 0:
        raise ValueError("trading_cost_pct cannot be negative.")

    clean_prices = price_data.dropna(subset=["Open", "Close"]).copy()

    if len(clean_prices) < 2:
        return _empty_result(cleaned_symbol)

    features = build_features(clean_prices)

    # No signal is possible until every required feature exists (MA50 plus its
    # 5-day slope). Start the backtest on that row so the strategy and
    # buy-and-hold are measured over the same days.
    tradeable_rows = features[REQUIRED_FEATURE_COLUMNS].notna().all(axis=1).to_numpy()
    start = int(tradeable_rows.argmax()) if tradeable_rows.any() else len(features)

    if start >= len(features) - 1:
        return _empty_result(cleaned_symbol)

    opens = clean_prices["Open"].to_numpy()
    closes = clean_prices["Close"].to_numpy()

    signal_counts = {signal: 0 for signal in SIGNALS}
    daily_returns = []
    exposures = []
    total_trading_costs = 0.0
    trades = 0
    held = 0.0  # fraction of the portfolio currently in the stock

    for index in range(start, len(features) - 1):
        # Only this day's row is needed. From `start` on, every row has all
        # required features (NaNs occur only during warm-up, because rows
        # without Open/Close were dropped before the features were built),
        # so the signal function's "latest complete row" is this row.
        # Passing the whole history so far gave identical signals at O(n)
        # cost per day.
        signal_result = generate_signal_from_features(
            cleaned_symbol,
            features.iloc[index : index + 1],
            log_decision=False,
        )
        signal = signal_result["signal"]
        signal_counts[signal] += 1
        target = make_decision(signal, signal_result["confidence"], 1.0)["position_pct"]

        # The old position is held overnight; the order fills at the next open.
        overnight_return = (opens[index + 1] / closes[index]) - 1
        next_day_return = (closes[index + 1] / opens[index + 1]) - 1

        cost = abs(target - held) * trading_cost_pct
        if target != held:
            trades += 1

        daily_returns.append(held * overnight_return + target * next_day_return - cost)
        exposures.append(target)
        total_trading_costs += cost
        held = target

    returns = pd.Series(daily_returns)
    cumulative_strategy_return = (returns + 1).prod() - 1
    buy_and_hold_return = (closes[-1] / closes[start]) - 1

    return {
        "symbol": cleaned_symbol,
        "buy_signals": signal_counts["BUY"],
        "sell_signals": signal_counts["SELL"],
        "hold_signals": signal_counts["HOLD"],
        "cumulative_strategy_return": float(round(cumulative_strategy_return, 4)),
        "buy_and_hold_return": float(round(buy_and_hold_return, 4)),
        "sharpe_ratio": _annualized_sharpe(returns),
        "max_drawdown": _max_drawdown(returns),
        "trades": trades,
        # Costs are tiny at 0-10% position sizes, so keep more decimals.
        "total_trading_costs": float(round(total_trading_costs, 6)),
        "average_exposure": float(round(sum(exposures) / len(exposures), 4)),
    }
