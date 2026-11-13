from pydantic import BaseModel, Field

from schemas.common import SymbolRequest

# Upper bound on portfolio_value, in currency units: generous for any paper
# portfolio while rejecting values that can only be mistakes.
MAX_PORTFOLIO_VALUE = 1_000_000_000


class Decision(BaseModel):
    position_pct: float
    position_value: float


class SignalRequest(SymbolRequest):
    portfolio_value: float = Field(
        default=10000,
        gt=0,
        le=MAX_PORTFOLIO_VALUE,
        allow_inf_nan=False,
        description="Portfolio value the position is sized against. Must be positive.",
    )


class SignalResponse(BaseModel):
    symbol: str
    signal: str
    confidence: float
    decision: Decision
    macd_line: float | None = None
    signal_line: float | None = None
    histogram: float | None = None
