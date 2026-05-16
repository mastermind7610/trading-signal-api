from fastapi import APIRouter, HTTPException
from schemas.signal import SignalRequest, SignalResponse
from services.signal import generate_signal

router = APIRouter()

@router.post("/signal", response_model=SignalResponse)
def get_signal(request: SignalRequest):
    try:
        return generate_signal(request.symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
