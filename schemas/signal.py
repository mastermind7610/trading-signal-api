from pydantic import BaseModel

class SignalRequest(BaseModel):
    symbol: str

class SignalResponse(BaseModel):
    symbol: str
    signal: str
    confidence: float