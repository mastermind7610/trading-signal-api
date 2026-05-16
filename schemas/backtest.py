from pydantic import BaseModel


class BacktestRequest(BaseModel):
    symbol: str


class BacktestResponse(BaseModel):
    symbol: str
    buy_signals: int
    sell_signals: int
    hold_signals: int
    cumulative_strategy_return: float
    buy_and_hold_return: float
