"""Strategy variants with switchable overrides, and the backtest's accounting.

The signal rules copy services/signal.py and the accounting copies
services/backtest.py; the features, confidence, position sizing, Sharpe
ratio and drawdown are the production functions themselves.
research/verify_engine.py checks that the full strategy here reproduces
run_backtest exactly before any result is trusted.

Nothing here reads past research.config.TUNING_LAST_DAY unless it is asked
for the holdout window, which only research/run_holdout.py does.
"""

import hashlib
import json
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from research.config import DATA_DIR, MANIFEST_PATH, TRADING_COST_PCT, TUNING_LAST_DAY
from services.backtest import _annualized_sharpe, _max_drawdown
from services.decisions import make_decision
from services.features import build_features
from services.signal import REQUIRED_FEATURE_COLUMNS, compute_confidence

BUY, SELL, HOLD = "BUY", "SELL", "HOLD"

# The overrides in the order services/signal.py checks them, each with the
# crossover signal it can turn into HOLD.
OVERRIDES = {
    "sell_trend_rising": SELL,
    "buy_trend_falling": BUY,
    "sell_price_above_ma50": SELL,
    "buy_overbought": BUY,
    "sell_oversold": SELL,
    "buy_macd_bearish": BUY,
    "sell_macd_bullish": SELL,
}

TUNING = "tuning"
HOLDOUT = "holdout"


@dataclass(frozen=True)
class Variant:
    name: str
    overrides: frozenset[str]
    buy_and_hold: bool = False


def all_variants() -> list[Variant]:
    """Buy-and-hold, then the 16 strategy variants, in table order."""
    every = frozenset(OVERRIDES)
    variants = [
        Variant("buy_and_hold", frozenset(), buy_and_hold=True),
        Variant("bare", frozenset()),
        Variant("full", every),
    ]
    variants += [Variant(f"full_minus_{code}", every - {code}) for code in OVERRIDES]
    variants += [Variant(f"bare_plus_{code}", frozenset({code})) for code in OVERRIDES]
    return variants


def variant_by_name(name: str) -> Variant:
    for variant in all_variants():
        if variant.name == name:
            return variant
    raise KeyError(name)


def load_prices(symbol: str) -> pd.DataFrame:
    """The cached bars for a symbol, after checking them against the manifest."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    entry = manifest["files"][symbol]
    path = DATA_DIR / entry["file"]

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != entry["sha256"]:
        raise RuntimeError(f"{path} does not match its manifest hash; the cached data changed")

    prices = pd.read_csv(path, index_col="Date", parse_dates=True, float_precision="round_trip")
    if prices[["Open", "Close"]].isna().any().any():
        raise RuntimeError(f"{path} has missing Open or Close values")
    return prices


def window_prices(symbol: str, window: str) -> tuple[pd.DataFrame, int]:
    """Prices for a window and the index of its first signal day.

    Tuning: rows up to TUNING_LAST_DAY only, and the first signal day is the
    first with every feature, as in run_backtest. Holdout: every row, so the
    indicators warm up on earlier prices, and the first signal day is
    TUNING_LAST_DAY, whose close sets the position for the first holdout day.
    """
    prices = load_prices(symbol)
    last_tuning = pd.Timestamp(TUNING_LAST_DAY)

    if window == TUNING:
        prices = prices.loc[:last_tuning]
        features = build_features(prices)
        complete = features[REQUIRED_FEATURE_COLUMNS].notna().all(axis=1).to_numpy()
        return prices, int(complete.argmax())

    if window == HOLDOUT:
        return prices, int(prices.index.get_loc(last_tuning))

    raise ValueError(f"unknown window: {window}")


@dataclass
class SignalInputs:
    """Per-row ingredients of the signal, shared by every variant."""

    crossover: np.ndarray  # BUY, SELL or HOLD before any override
    conditions: dict[str, np.ndarray]  # override code -> its condition holds
    buy_target: np.ndarray  # position a BUY holds on that row


def signal_inputs(prices: pd.DataFrame) -> SignalInputs:
    features = build_features(prices)

    ma_20 = features["ma_20"].to_numpy()
    ma_50 = features["ma_50"].to_numpy()
    volatility = features["rolling_volatility"].to_numpy()
    # The neutral defaults services/signal.py uses for missing values.
    trend_slope = features["trend_slope"].fillna(0.0).to_numpy()
    price_position = features["price_position"].fillna(0.0).to_numpy()
    rsi = features["rsi"].fillna(50.0).to_numpy()
    macd_histogram = features["macd_histogram"].fillna(0.0).to_numpy()

    usable = features[REQUIRED_FEATURE_COLUMNS].notna().all(axis=1).to_numpy() & (ma_50 != 0)
    buy_target = np.zeros(len(features))

    for row in np.flatnonzero(usable):
        confidence = compute_confidence(ma_20[row], ma_50[row], volatility[row])
        if not math.isfinite(confidence):
            # services/signal.py answers HOLD on a non-finite confidence.
            usable[row] = False
            continue
        buy_target[row] = make_decision(BUY, confidence, 1.0)["position_pct"]

    crossover = np.full(len(features), HOLD, dtype=object)
    crossover[usable & (ma_20 > ma_50)] = BUY
    crossover[usable & (ma_20 < ma_50)] = SELL

    conditions = {
        "sell_trend_rising": trend_slope > 0.01,
        "buy_trend_falling": trend_slope < -0.01,
        "sell_price_above_ma50": price_position > 0.05,
        "buy_overbought": rsi > 70,
        "sell_oversold": rsi < 30,
        "buy_macd_bearish": macd_histogram < 0,
        "sell_macd_bullish": macd_histogram > 0,
    }
    return SignalInputs(crossover=crossover, conditions=conditions, buy_target=buy_target)


def variant_signals(inputs: SignalInputs, overrides: frozenset[str]) -> np.ndarray:
    # Each override only turns its side's signal into HOLD, so the order they
    # are applied in does not change the final signal (only the reason code,
    # which is not needed here).
    signals = inputs.crossover.copy()
    for code in overrides:
        signals[(signals == OVERRIDES[code]) & inputs.conditions[code]] = HOLD
    return signals


def variant_targets(inputs: SignalInputs, variant: Variant) -> np.ndarray:
    if variant.buy_and_hold:
        return np.ones(len(inputs.crossover))
    signals = variant_signals(inputs, variant.overrides)
    return np.where(signals == BUY, inputs.buy_target, 0.0)


def simulate(
    prices: pd.DataFrame,
    targets: np.ndarray,
    first: int,
    trading_cost_pct: float = TRADING_COST_PCT,
) -> dict:
    """run_backtest's accounting for a target position per signal day.

    Starts flat at the close of row `first`. The target set at row i's close
    fills at row i+1's open; the old position earns the overnight move and
    the new one the open-to-close move; each change pays the cost on the
    amount traded. The returned daily returns are indexed by the day earned.
    """
    opens = prices["Open"].to_numpy()
    closes = prices["Close"].to_numpy()

    daily_returns = []
    exposures = []
    total_trading_costs = 0.0
    trades = 0
    held = 0.0

    for index in range(first, len(prices) - 1):
        target = float(targets[index])
        overnight_return = (opens[index + 1] / closes[index]) - 1
        next_day_return = (closes[index + 1] / opens[index + 1]) - 1

        cost = abs(target - held) * trading_cost_pct
        if target != held:
            trades += 1

        daily_returns.append(held * overnight_return + target * next_day_return - cost)
        exposures.append(target)
        total_trading_costs += cost
        held = target

    returns = pd.Series(daily_returns, index=prices.index[first + 1 :])
    return {
        "returns": returns,
        "total_return": float((returns + 1).prod() - 1),
        "sharpe": _annualized_sharpe(returns),
        "max_drawdown": _max_drawdown(returns),
        "exposure": sum(exposures) / len(exposures),
        "trades": trades,
        "total_trading_costs": total_trading_costs,
        "first_return_day": returns.index[0].date().isoformat(),
        "last_return_day": returns.index[-1].date().isoformat(),
        "days": len(returns),
    }
