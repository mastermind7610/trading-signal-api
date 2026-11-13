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
