from fastapi import APIRouter, Depends, HTTPException

from routes.auth import require_api_key
from schemas.backtest import BacktestRequest, BacktestResponse
from schemas.common import MARKET_DATA_ERROR_RESPONSES
from services.backtest import run_backtest
from services.data import get_price_data

router = APIRouter(tags=["backtests"], dependencies=[Depends(require_api_key)])


@router.post(
    "/backtest",
    response_model=BacktestResponse,
    summary="Replay the signal strategy over daily history",
    responses=MARKET_DATA_ERROR_RESPONSES,
)
def backtest_signal(request: BacktestRequest):
    """Walk-forward, long-only backtest of the `/signal` strategy.

    Each day's signal uses data up to that close and fills at the next open.
    Every change in position pays `trading_cost_pct`. Buy-and-hold is measured
    over the same days.
    """
    try:
        price_data = get_price_data(request.symbol, period=request.period)
        return run_backtest(
            request.symbol,
            price_data,
            trading_cost_pct=request.trading_cost_pct,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
