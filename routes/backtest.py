from fastapi import APIRouter, HTTPException

from schemas.backtest import BacktestRequest, BacktestResponse
from services.backtest import run_backtest
from services.data import get_price_data


router = APIRouter()


@router.post("/backtest", response_model=BacktestResponse)
def backtest_signal(request: BacktestRequest):
    try:
        price_data = get_price_data(request.symbol)
        return run_backtest(request.symbol, price_data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc