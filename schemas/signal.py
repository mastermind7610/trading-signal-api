from pydantic import BaseModel


class Decision(BaseModel):
    position_pct: float
    position_value: float


class SignalRequest(BaseModel):
    symbol: str
    portfolio_value: float = 10000


class SignalResponse(BaseModel):
    symbol: str
    signal: str
    confidence: float
    decision: Decision
