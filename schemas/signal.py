from pydantic import BaseModel, ConfigDict, Field

from schemas.common import SymbolRequest

# Upper bound on portfolio_value, in currency units: generous for any paper
# portfolio while rejecting values that can only be mistakes.
MAX_PORTFOLIO_VALUE = 1_000_000_000


class Decision(BaseModel):
    position_pct: float = Field(
        description="Fraction of the portfolio to hold in the symbol (0 to 0.10)."
    )
    position_value: float = Field(description="position_pct applied to portfolio_value.")


class SignalRequest(SymbolRequest):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"symbol": "AAPL", "portfolio_value": 10000}]}
    )

    portfolio_value: float = Field(
        default=10000,
        gt=0,
        le=MAX_PORTFOLIO_VALUE,
        allow_inf_nan=False,
        description="Portfolio value the position is sized against. Must be positive.",
    )


class SignalResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "symbol": "AAPL",
                    "signal": "HOLD",
                    "confidence": 0.5,
                    "reason": "buy_vetoed_macd_bearish",
                    "explanation": (
                        "HOLD as of 2026-11-23. The 20-day average is 1.7% above the "
                        "50-day, 0.9 times the typical daily move of 1.8%: a bullish "
                        "crossover, but the BUY was held back because the MACD "
                        "histogram is -0.74, below zero, so momentum disagrees with "
                        "the crossover. No position."
                    ),
                    "decision": {"position_pct": 0.0, "position_value": 0.0},
                    "rsi": 63.3,
                    "macd_line": 2.55,
                    "signal_line": 3.2916,
                    "histogram": -0.7417,
                }
            ]
        }
    )

    symbol: str = Field(description="Normalized (upper-cased) symbol.")
    signal: str = Field(description="BUY, SELL or HOLD.")
    confidence: float = Field(
        description="0.5 to 0.95: how decisive the moving-average crossover is."
    )
    reason: str = Field(
        description=(
            "Machine-readable code for why this signal was produced: the "
            "crossover basis, the veto that downgraded it to HOLD, or the "
            "fallback that forced HOLD. See the README's Signal Logic section."
        )
    )
    explanation: str = Field(
        description=(
            "Plain-English account of how the signal was reached, written from "
            "the same indicator values and thresholds that decided it. Names the "
            "one veto responsible when a BUY was held back. See the README's "
            "Explanation section."
        )
    )
    decision: Decision
    rsi: float | None = Field(
        default=None,
        description="Latest 14-day RSI (0–100); null with too little history.",
    )
    macd_line: float | None = Field(
        default=None, description="Latest MACD line (12/26/9); null with too little history."
    )
    signal_line: float | None = Field(
        default=None, description="Latest MACD signal line; null with too little history."
    )
    histogram: float | None = Field(
        default=None, description="MACD line minus signal line; null with too little history."
    )
