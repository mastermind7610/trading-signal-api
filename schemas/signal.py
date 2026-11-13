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
                    "signal": "BUY",
                    "confidence": 0.68,
                    "decision": {"position_pct": 0.04, "position_value": 400.0},
                    "macd_line": 3.7935,
                    "signal_line": 3.0584,
                    "histogram": 0.7352,
                }
            ]
        }
    )

    symbol: str = Field(description="Normalized (upper-cased) symbol.")
    signal: str = Field(description="BUY, SELL or HOLD.")
    confidence: float = Field(
        description="0.5 to 0.95: how decisive the moving-average crossover is."
    )
    decision: Decision
    macd_line: float | None = Field(
        default=None, description="Latest MACD line (12/26/9); null with too little history."
    )
    signal_line: float | None = Field(
        default=None, description="Latest MACD signal line; null with too little history."
    )
    histogram: float | None = Field(
        default=None, description="MACD line minus signal line; null with too little history."
    )
