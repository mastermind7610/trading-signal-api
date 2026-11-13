import math

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from routes.signal import router as signal_router
from routes.backtest import router as backtest_router
from services.data import MarketDataUnavailableError, NoPriceDataError

# Sent with every 503 so well-behaved clients know when to retry.
RETRY_AFTER_SECONDS = 30

app = FastAPI()

app.include_router(signal_router)
app.include_router(backtest_router)


def _json_safe(value):
    """Render non-finite floats as text so an error body can always be serialized."""
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request: Request, exc: RequestValidationError):
    # Pydantic echoes the offending input in each error. Python's JSON parser
    # accepts NaN and Infinity, which the JSON response layer then refuses to
    # serialize, so without this a request carrying NaN would get a 500
    # instead of the 422 it deserves.
    return JSONResponse(
        status_code=422,
        content={"detail": _json_safe(jsonable_encoder(exc.errors()))},
    )


@app.exception_handler(NoPriceDataError)
async def no_price_data_handler(request: Request, exc: NoPriceDataError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(MarketDataUnavailableError)
async def market_data_unavailable_handler(request: Request, exc: MarketDataUnavailableError):
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc)},
        headers={"Retry-After": str(RETRY_AFTER_SECONDS)},
    )


@app.get("/health")
def health():
    return {"status": "ok"}
