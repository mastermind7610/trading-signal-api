from dataclasses import asdict
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException

from pipeline.mongo_repository import (
    MONGODB_URI_ENV_VAR,
    MongoLedgerRepository,
    configured_mongodb_uri,
    ledger_repository_from_uri,
)
from pipeline.repository import LedgerEntry, LedgerRepository
from routes.auth import require_api_key
from schemas.common import SymbolPath
from schemas.ledger import LEDGER_ERROR_RESPONSES, LedgerResponse

router = APIRouter(tags=["ledger"], dependencies=[Depends(require_api_key)])


@lru_cache(maxsize=1)
def _repository_for(uri: str) -> MongoLedgerRepository:
    # The MongoDB client behind a repository keeps a pool of connections, so
    # one is built per process and reused by every request. Keyed by the
    # connection string, so a different string would get its own client.
    return ledger_repository_from_uri(uri)


def get_ledger_repository() -> LedgerRepository:
    """The ledger this server reads, from the configured MongoDB.

    Without a connection string the route answers 503, as the protected
    routes do without an API key, rather than failing on first use.
    """
    uri = configured_mongodb_uri()

    if uri is None:
        raise HTTPException(
            status_code=503,
            detail=f"The ledger is not configured: set {MONGODB_URI_ENV_VAR} on the server.",
        )

    return _repository_for(uri)


def _entry_fields(entry: LedgerEntry) -> dict:
    """The entry as the flat record the response reports."""
    return {
        "trade_date": entry.trade_date,
        "signal_date": entry.signal_date,
        "signal": entry.signal,
        "confidence": entry.confidence,
        "reason": entry.reason,
        "prev_close": entry.prev_close,
        "open_price": entry.open_price,
        "close_price": entry.close_price,
        **asdict(entry.day),
    }


@router.get(
    "/ledger/{symbol}",
    response_model=LedgerResponse,
    summary="Paper-trading ledger for a symbol",
    responses=LEDGER_ERROR_RESPONSES,
)
def read_ledger(
    symbol: SymbolPath,
    repository: LedgerRepository = Depends(get_ledger_repository),
):
    """Every trading day the daily run has recorded for the symbol, oldest first.

    Each entry gives the signal that set the position, the prices the day
    was accounted with, and the paper account at the close. The rules are
    the backtest's: the signal from one close fills at the next open, and
    every change in position pays the trading cost.

    This endpoint only reads. The ledger is written by the daily run, not
    through the API.
    """
    entries = repository.history(symbol)

    if not entries:
        raise HTTPException(status_code=404, detail=f"No ledger found for symbol: {symbol}")

    return {"symbol": symbol, "entries": [_entry_fields(entry) for entry in entries]}
