import json
import logging
import math
from typing import Any

import pandas as pd

from services.data import get_price_data
from services.decisions import CONFIDENCE_MAX, CONFIDENCE_MIN, make_decision
from services.features import build_features

logger = logging.getLogger(__name__)

MIN_REQUIRED_ROWS = 50
DEFAULT_HOLD_CONFIDENCE = CONFIDENCE_MIN
REQUIRED_FEATURE_COLUMNS = ["Close", "ma_20", "ma_50", "rolling_volatility", "trend_slope", "price_position"]
# How decisive a crossover must be to earn CONFIDENCE_MAX: the gap between
# the moving averages measured in units of 20-day daily volatility. On five
# years of SPY, AAPL, MSFT and NVDA the median BUY day sits near 1.7 and the
# top quarter above 3, so 3 maps a typical BUY to about 0.75 and a clearly
# established trend to the cap.
FULL_CONFIDENCE_STRENGTH = 3.0


def _safe_float(value: Any) -> float | None:
    if pd.isna(value):
        return None

    return float(value)


def _latest_macd(row: Any) -> dict:
    # Reads the compute_macd output that build_features already stored on the
    # row; NaN (thin history) or absent columns come back as None.
    return {
        "macd_line": _safe_float(row.get("macd")),
        "signal_line": _safe_float(row.get("macd_signal")),
        "histogram": _safe_float(row.get("macd_histogram")),
    }


def compute_confidence(ma_20: float, ma_50: float, rolling_volatility: float) -> float:
    """Confidence in a crossover, in [CONFIDENCE_MIN, CONFIDENCE_MAX].

    The gap between the moving averages is measured in units of daily
    volatility, so a 2% gap counts for a lot when prices move 0.5% a day and
    for little when they move 3% a day. Confidence rises linearly with that
    ratio, from CONFIDENCE_MIN at no gap to CONFIDENCE_MAX at
    FULL_CONFIDENCE_STRENGTH, and is capped there. Because the ratio is
    scale-free, the same confidence means the same thing on a calm index
    fund and a volatile single stock.

    Callers must guard ma_50 == 0. Zero volatility with a non-zero gap is a
    perfectly steady trend and earns CONFIDENCE_MAX.
    """
    spread = abs(ma_20 - ma_50) / abs(ma_50)

    if rolling_volatility > 0:
        strength = spread / rolling_volatility
    elif spread > 0:
        strength = math.inf
    else:
        strength = 0.0

    # Explicit comparison rather than min() so a NaN input propagates to the
    # finiteness check in generate_signal_from_features instead of silently
    # becoming the cap.
    scaled = strength / FULL_CONFIDENCE_STRENGTH
    if scaled > 1.0:
        scaled = 1.0

    confidence = CONFIDENCE_MIN + (CONFIDENCE_MAX - CONFIDENCE_MIN) * scaled
    return float(round(confidence, 2))


def _log_signal_decision(
    symbol: str,
    latest_close: float | None,
    ma_20: float | None,
    ma_50: float | None,
    rolling_volatility: float | None,
    signal: str,
    confidence: float,
    reason: str,
) -> None:
    payload = {
        "symbol": symbol,
        "latest_close": latest_close,
        "ma_20": ma_20,
        "ma_50": ma_50,
        "rolling_volatility": rolling_volatility,
        "signal": signal,
        "confidence": confidence,
        "reason": reason,
    }

    logger.info(
        "trading_signal_generated %s",
        json.dumps(payload),
        extra=payload,
    )


def _hold_response(
    symbol: str,
    reason: str,
    latest_close: float | None = None,
    ma_20: float | None = None,
    ma_50: float | None = None,
    rolling_volatility: float | None = None,
    macd: dict | None = None,
    log_decision: bool = True,
) -> dict:
    if log_decision:
        _log_signal_decision(
            symbol=symbol,
            latest_close=latest_close,
            ma_20=ma_20,
            ma_50=ma_50,
            rolling_volatility=rolling_volatility,
            signal="HOLD",
            confidence=DEFAULT_HOLD_CONFIDENCE,
            reason=reason,
        )

    return {
        "symbol": symbol,
        "signal": "HOLD",
        "confidence": DEFAULT_HOLD_CONFIDENCE,
        **(macd or _latest_macd({})),
    }


def generate_signal_from_features(
    symbol: str,
    features: pd.DataFrame,
    log_decision: bool = True,
) -> dict:
    cleaned_symbol = symbol.strip().upper()

    missing_columns = [
        column for column in REQUIRED_FEATURE_COLUMNS if column not in features.columns
    ]

    if missing_columns:
        if log_decision:
            logger.warning(
                "trading_signal_missing_feature_columns",
                extra={
                    "symbol": cleaned_symbol,
                    "missing_columns": missing_columns,
                },
            )

        return _hold_response(
            symbol=cleaned_symbol,
            reason="missing_feature_columns",
            log_decision=log_decision,
        )

    latest_features = features.dropna(subset=REQUIRED_FEATURE_COLUMNS).tail(1)

    if latest_features.empty:
        latest_row = features.tail(1).iloc[0] if not features.empty else {}

        return _hold_response(
            symbol=cleaned_symbol,
            reason="insufficient_feature_data",
            latest_close=_safe_float(latest_row.get("Close")),
            ma_20=_safe_float(latest_row.get("ma_20")),
            ma_50=_safe_float(latest_row.get("ma_50")),
            rolling_volatility=_safe_float(latest_row.get("rolling_volatility")),
            macd=_latest_macd(latest_row),
            log_decision=log_decision,
        )

    latest = latest_features.iloc[0]

    latest_close = _safe_float(latest["Close"])
    ma_20 = _safe_float(latest["ma_20"])
    ma_50 = _safe_float(latest["ma_50"])
    rolling_volatility = _safe_float(latest["rolling_volatility"])
    macd = _latest_macd(latest)

    if (
        latest_close is None
        or ma_20 is None
        or ma_50 is None
        or rolling_volatility is None
        or ma_50 == 0
    ):
        return _hold_response(
            symbol=cleaned_symbol,
            reason="invalid_feature_values",
            latest_close=latest_close,
            ma_20=ma_20,
            ma_50=ma_50,
            rolling_volatility=rolling_volatility,
            macd=macd,
            log_decision=log_decision,
        )

    trend_slope = _safe_float(latest.get("trend_slope")) or 0.0
    price_position = _safe_float(latest.get("price_position")) or 0.0

    rsi = _safe_float(latest.get("rsi"))
    if rsi is None:
        rsi = 50.0  # neutral default when RSI is unavailable

    macd_histogram = macd["histogram"]
    if macd_histogram is None:
        macd_histogram = 0.0  # neutral default when MACD is unavailable

    if ma_20 > ma_50:
        signal = "BUY"
    elif ma_20 < ma_50:
        signal = "SELL"
    else:
        signal = "HOLD"

    # Override: don't SELL if trend is still rising
    if signal == "SELL" and trend_slope > 0.01:
        signal = "HOLD"

    # Override: don't BUY if trend is falling hard
    if signal == "BUY" and trend_slope < -0.01:
        signal = "HOLD"

    # Override: don't SELL if price is well above MA50 (strong uptrend)
    if signal == "SELL" and price_position > 0.05:
        signal = "HOLD"

    # Override: don't BUY if overbought (RSI > 70)
    if signal == "BUY" and rsi > 70:
        signal = "HOLD"

    # Override: don't SELL if oversold (RSI < 30)
    if signal == "SELL" and rsi < 30:
        signal = "HOLD"

    # Override: don't BUY if MACD momentum disagrees with the crossover
    # (negative histogram = MACD line below its signal line = bearish momentum)
    if signal == "BUY" and macd_histogram < 0:
        signal = "HOLD"

    # Override: don't SELL if MACD momentum disagrees with the crossover
    # (positive histogram = MACD line above its signal line = bullish momentum)
    if signal == "SELL" and macd_histogram > 0:
        signal = "HOLD"

    confidence = compute_confidence(ma_20, ma_50, rolling_volatility)

    if not math.isfinite(confidence):
        return _hold_response(
            symbol=cleaned_symbol,
            reason="invalid_confidence",
            latest_close=latest_close,
            ma_20=ma_20,
            ma_50=ma_50,
            rolling_volatility=rolling_volatility,
            macd=macd,
            log_decision=log_decision,
        )

    if log_decision:
        _log_signal_decision(
            symbol=cleaned_symbol,
            latest_close=latest_close,
            ma_20=ma_20,
            ma_50=ma_50,
            rolling_volatility=rolling_volatility,
            signal=signal,
            confidence=confidence,
            reason="signal_generated",
        )

    return {
        "symbol": cleaned_symbol,
        "signal": signal,
        "confidence": confidence,
        **macd,
    }


def generate_signal(symbol: str, portfolio_value: float = 10000) -> dict:
    cleaned_symbol = symbol.strip().upper()

    price_data = get_price_data(cleaned_symbol)

    if len(price_data) < MIN_REQUIRED_ROWS:
        latest_close = (
            _safe_float(price_data["Close"].iloc[-1])
            if "Close" in price_data.columns and not price_data.empty
            else None
        )

        result = _hold_response(
            symbol=cleaned_symbol,
            reason="insufficient_price_history",
            latest_close=latest_close,
        )
    else:
        features = build_features(price_data)
        result = generate_signal_from_features(
            symbol=cleaned_symbol,
            features=features,
        )

    result["decision"] = make_decision(result["signal"], result["confidence"], portfolio_value)
    return result