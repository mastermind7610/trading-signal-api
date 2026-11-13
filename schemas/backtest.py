from typing import Literal

from pydantic import BaseModel, Field

from schemas.common import SymbolRequest
from services.backtest import DEFAULT_TRADING_COST_PCT


class BacktestRequest(SymbolRequest):
    # How much daily history to fetch. The first ~54 trading days are
    # indicator warm-up, so short periods leave very few days to test.
    period: Literal["6mo", "1y", "2y", "5y", "10y"] = "5y"
    # Commission plus slippage, as a fraction of the amount traded (0.001 = 0.1%).
    trading_cost_pct: float = Field(default=DEFAULT_TRADING_COST_PCT, ge=0, le=0.05)


class BacktestResponse(BaseModel):
    symbol: str
    buy_signals: int
    sell_signals: int
    hold_signals: int
    cumulative_strategy_return: float
    buy_and_hold_return: float
    sharpe_ratio: float
    max_drawdown: float
    trades: int
    total_trading_costs: float
    average_exposure: float
