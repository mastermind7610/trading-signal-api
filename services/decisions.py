MAX_POSITION_PCT = 0.10
# Confidence is reported in this range. CONFIDENCE_MIN means no conviction
# (every HOLD fallback reports it) and sizes a BUY at zero; CONFIDENCE_MAX
# sizes a BUY at MAX_POSITION_PCT.
CONFIDENCE_MIN = 0.5
CONFIDENCE_MAX = 0.95


def make_decision(signal: str, confidence: float, portfolio_value: float) -> dict:
    """Target position for a signal, as a fraction of the portfolio.

    Long-only: BUY holds a position sized by confidence; SELL and HOLD both
    mean hold nothing (cash). There is no short selling.
    """
    if signal == "BUY":
        scaled = (confidence - CONFIDENCE_MIN) / (CONFIDENCE_MAX - CONFIDENCE_MIN)
        position_pct = round(min(MAX_POSITION_PCT, max(0.0, scaled * MAX_POSITION_PCT)), 4)
    else:
        position_pct = 0.0

    return {
        "position_pct": position_pct,
        "position_value": round(position_pct * portfolio_value, 2),
    }
