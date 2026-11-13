from pydantic import BaseModel, Field, field_validator

# Yahoo Finance ticker syntax: letters and digits, plus "." or "-" for share
# classes (BRK.B, BRK-B), "^" for indices (^GSPC) and "=" for FX and futures
# (EURUSD=X, ES=F). Whitespace is stripped and the symbol upper-cased before
# the pattern is checked, so " aapl " is accepted and echoed back as "AAPL".
SYMBOL_MAX_LENGTH = 12
SYMBOL_PATTERN = r"^[A-Z0-9.\-^=]+$"


class SymbolRequest(BaseModel):
    """Base request for endpoints that take a ticker symbol."""

    symbol: str = Field(
        min_length=1,
        max_length=SYMBOL_MAX_LENGTH,
        pattern=SYMBOL_PATTERN,
        description="Ticker symbol as used by Yahoo Finance, e.g. AAPL, BRK-B, ^GSPC.",
        examples=["AAPL"],
    )

    @field_validator("symbol", mode="before")
    @classmethod
    def _normalize_symbol(cls, value):
        # Runs before the length and pattern checks, so "  aapl " passes and
        # "   " fails min_length rather than slipping through as whitespace.
        if isinstance(value, str):
            return value.strip().upper()
        return value


class ErrorResponse(BaseModel):
    """Body of the 400, 404 and 503 errors the service raises itself."""

    detail: str = Field(
        description="What went wrong.",
        examples=["No price data found for symbol: XYZ"],
    )


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])
    version: str = Field(description="Deployed API version.", examples=["1.0.0"])


# Documented on every route that fetches prices. 422 is added by FastAPI.
MARKET_DATA_ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "The request could not be processed."},
    404: {
        "model": ErrorResponse,
        "description": (
            "Yahoo Finance returned no price data for the symbol. This also "
            "happens when Yahoo rate-limits requests."
        ),
    },
    503: {
        "model": ErrorResponse,
        "description": "Yahoo Finance could not be reached. Retry after the `Retry-After` delay.",
    },
}
