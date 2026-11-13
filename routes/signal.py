from fastapi import APIRouter, HTTPException

from schemas.common import MARKET_DATA_ERROR_RESPONSES
from schemas.signal import SignalRequest, SignalResponse
from services.signal import generate_signal

router = APIRouter(tags=["signals"])


@router.post(
    "/signal",
    response_model=SignalResponse,
    summary="Current signal and position size for a symbol",
    responses=MARKET_DATA_ERROR_RESPONSES,
)
def get_signal(request: SignalRequest):
    """BUY, SELL or HOLD from the latest six months of daily prices.

    The `decision` block sizes a long-only position from the confidence score,
    capped at 10% of `portfolio_value`. SELL and HOLD both mean cash.
    """
    try:
        return generate_signal(request.symbol, request.portfolio_value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
