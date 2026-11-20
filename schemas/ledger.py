from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from schemas.common import ErrorResponse


class LedgerEntryResponse(BaseModel):
    """One trading day of a symbol's paper account."""

    trade_date: date = Field(
        description="The trading day: the order filled at its open and the account "
        "is valued at its close."
    )
    signal_date: date = Field(
        description="The previous trading day, whose close produced the signal."
    )
    signal: str = Field(description="BUY, SELL or HOLD, as `/signal` reports it.")
    confidence: float = Field(description="0.5 to 0.95, as `/signal` reports it.")
    reason: str = Field(description="Reason code for the signal, as `/signal` reports it.")
    prev_close: float = Field(description="Close on `signal_date`.")
    open_price: float = Field(description="Open on `trade_date`, where the order filled.")
    close_price: float = Field(description="Close on `trade_date`.")
    position_before: float = Field(
        description="Fraction of the account in the symbol before the fill (held overnight)."
    )
    position_after: float = Field(
        description="Fraction of the account in the symbol after the fill (0 to 0.10)."
    )
    traded_pct: float = Field(description="Size of the fill, as a fraction of the account.")
    traded: bool = Field(description="Whether the position changed.")
    cost_pct: float = Field(description="Trading cost paid, as a fraction of the account.")
    daily_return: float = Field(
        description="The account's return for the day, after costs, as a decimal."
    )
    equity: float = Field(description="Account value at the close.")
    position_value: float = Field(description="Part of `equity` held in the symbol.")
    cash: float = Field(description="Part of `equity` held in cash.")


class LedgerResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "symbol": "AAPL",
                    "entries": [
                        {
                            "trade_date": "2026-11-13",
                            "signal_date": "2026-11-12",
                            "signal": "BUY",
                            "confidence": 0.68,
                            "reason": "ma_crossover_bullish",
                            "prev_close": 354.88,
                            "open_price": 357.96,
                            "close_price": 356.27,
                            "position_before": 0.0,
                            "position_after": 0.04,
                            "traded_pct": 0.04,
                            "traded": True,
                            "cost_pct": 0.00004,
                            "daily_return": -0.000229,
                            "equity": 9997.71,
                            "position_value": 399.91,
                            "cash": 9597.8,
                        }
                    ],
                }
            ]
        }
    )

    symbol: str = Field(description="Normalized (upper-cased) symbol.")
    entries: list[LedgerEntryResponse] = Field(
        description="Every recorded trading day, oldest first."
    )


# 422 is added by FastAPI.
LEDGER_ERROR_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Missing or invalid `X-API-Key` header."},
    404: {
        "model": ErrorResponse,
        "description": "The daily run has recorded no days for the symbol.",
    },
    503: {
        "model": ErrorResponse,
        "description": (
            "The ledger database could not be reached (retry after the "
            "`Retry-After` delay), or the database connection or the API key "
            "is not configured on the server."
        ),
    },
}
