import math

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from routes.backtest import router as backtest_router
from routes.signal import router as signal_router
from schemas.common import HealthResponse
from services.data import MarketDataUnavailableError, NoPriceDataError

# Single source of the API version: shown in the OpenAPI docs and returned by
# /health, so a deploy can be checked with one call.
API_VERSION = "0.9.0"

# Sent with every 503 so well-behaved clients know when to retry.
RETRY_AFTER_SECONDS = 30

API_DESCRIPTION = """
Paper-trading signals and backtests. **Research only: this service places no
orders and connects to no broker.**

* `POST /signal` turns a 20/50-day moving-average crossover, filtered by trend,
  RSI and MACD checks, into BUY / SELL / HOLD with a confidence score and a
  position size for the given portfolio.
* `POST /backtest` replays that same signal over daily history as a long-only
  strategy with next-day fills and trading costs, and compares it with
  buy-and-hold.

Prices come from Yahoo Finance. Errors use a single shape, `{"detail": "..."}`:
`404` when no price data is found for the symbol, `422` for invalid input and
`503` when Yahoo Finance cannot be reached.
"""

OPENAPI_TAGS = [
    {"name": "signals", "description": "Current trading signal and position size for one symbol."},
    {"name": "backtests", "description": "Historical replay of the signal strategy."},
    {"name": "health", "description": "Liveness and deployed version."},
]

app = FastAPI(
    title="TRADING_SIMMS",
    summary="Paper-trading signal and backtesting API.",
    description=API_DESCRIPTION,
    version=API_VERSION,
    openapi_tags=OPENAPI_TAGS,
)

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


@app.get(
    "/health",
    tags=["health"],
    summary="Liveness check",
    response_model=HealthResponse,
)
def health():
    """Returns `ok` and the deployed API version. Makes no upstream calls."""
    return {"status": "ok", "version": API_VERSION}
