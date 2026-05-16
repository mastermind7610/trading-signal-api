import json
import logging
import math
from typing import Any

import pandas as pd

from services.data import get_price_data
from services.features import build_features

logger = logging.getLogger(__name__)

MIN_REQUIRED_ROWS = 50
DEFAULT_HOLD_CONFIDENCE = 0.5
REQUIRED_FEATURE_COLUMNS = ["Close", "ma_20", "ma_50", "rolling_volatility"]


def _safe_float(value: Any) -> float | None:
    if pd.isna(value):
        return None

    return float(value)


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
            log_decision=log_decision,
        )

    latest = latest_features.iloc[0]

    latest_close = _safe_float(latest["Close"])
    ma_20 = _safe_float(latest["ma_20"])
    ma_50 = _safe_float(latest["ma_50"])
    rolling_volatility = _safe_float(latest["rolling_volatility"])

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
            log_decision=log_decision,
        )

    if ma_20 > ma_50:
        signal = "BUY"
    elif ma_20 < ma_50:
        signal = "SELL"
    else:
        signal = "HOLD"

    spread = abs(ma_20 - ma_50) / abs(ma_50)
    volatility_penalty = min(0.2, rolling_volatility)

    confidence = min(0.95, max(0.5, 0.5 + spread - volatility_penalty))
    confidence = float(round(confidence, 2))

    if not math.isfinite(confidence):
        return _hold_response(
            symbol=cleaned_symbol,
            reason="invalid_confidence",
            latest_close=latest_close,
            ma_20=ma_20,
            ma_50=ma_50,
            rolling_volatility=rolling_volatility,
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
    }


def generate_signal(symbol: str) -> dict:
    cleaned_symbol = symbol.strip().upper()

    price_data = get_price_data(cleaned_symbol)

    if len(price_data) < MIN_REQUIRED_ROWS:
        latest_close = (
            _safe_float(price_data["Close"].iloc[-1])
            if "Close" in price_data.columns and not price_data.empty
            else None
        )

        return _hold_response(
            symbol=cleaned_symbol,
            reason="insufficient_price_history",
            latest_close=latest_close,
        )

    features = build_features(price_data)

    return generate_signal_from_features(
        symbol=cleaned_symbol,
        features=features,
    )