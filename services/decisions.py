MAX_POSITION_PCT = 0.10
_CONFIDENCE_MIN = 0.5
_CONFIDENCE_MAX = 0.95


def make_decision(signal: str, confidence: float, portfolio_value: float) -> dict:
    if signal == "HOLD":
        position_pct = 0.0
    else:
        scaled = (confidence - _CONFIDENCE_MIN) / (_CONFIDENCE_MAX - _CONFIDENCE_MIN)
        position_pct = round(min(MAX_POSITION_PCT, max(0.0, scaled * MAX_POSITION_PCT)), 4)

    return {
        "position_pct": position_pct,
        "position_value": round(position_pct * portfolio_value, 2),
    }
