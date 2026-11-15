from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from schemas.common import SymbolRequest
from services.backtest import DEFAULT_TRADING_COST_PCT


class BacktestRequest(SymbolRequest):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"symbol": "AAPL", "period": "5y", "trading_cost_pct": 0.001}]
        }
    )

    period: Literal["6mo", "1y", "2y", "5y", "10y"] = Field(
        default="5y",
        description=(
            "How much daily history to test. The first ~54 trading days are "
            "indicator warm-up, so short periods leave very few days to test."
        ),
    )
    trading_cost_pct: float = Field(
        default=DEFAULT_TRADING_COST_PCT,
        ge=0,
        le=0.05,
        description="Commission plus slippage, as a fraction of the amount traded (0.001 = 0.1%).",
    )


class BacktestResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "symbol": "AAPL",
                    "buy_signals": 175,
                    "sell_signals": 153,
                    "hold_signals": 871,
                    "cumulative_strategy_return": 0.0029,
                    "buy_and_hold_return": 1.0677,
                    "sharpe_ratio": 0.102,
                    "max_drawdown": -0.008,
                    "trades": 177,
                    "total_trading_costs": 0.007587,
                    "average_exposure": 0.0088,
                }
            ]
        }
    )

    symbol: str
    buy_signals: int = Field(description="Days the signal was BUY.")
    sell_signals: int = Field(description="Days the signal was SELL (cash; long-only).")
    hold_signals: int = Field(description="Days the signal was HOLD (cash).")
    cumulative_strategy_return: float = Field(description="Strategy return as a decimal.")
    buy_and_hold_return: float = Field(
        description="Return from holding the symbol over the same days."
    )
    sharpe_ratio: float = Field(description="Annualized, risk-free rate 0; 0.0 when undefined.")
    max_drawdown: float = Field(description="Largest peak-to-trough fall, as a negative decimal.")
    trades: int = Field(description="Days the position size changed.")
    total_trading_costs: float = Field(description="Sum of costs, as a fraction of the portfolio.")
    average_exposure: float = Field(description="Average fraction of the portfolio invested.")
