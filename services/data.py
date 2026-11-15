import logging

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# Seconds to wait for Yahoo Finance before giving up on a request. Without a
# bound, a hung upstream would pin a worker thread for as long as it liked.
REQUEST_TIMEOUT_SECONDS = 10


class MarketDataError(Exception):
    """Base class for failures fetching market data."""


class MarketDataUnavailableError(MarketDataError):
    """Yahoo Finance could not be reached or returned an error."""


class NoPriceDataError(MarketDataError):
    """Yahoo Finance returned no rows for the symbol.

    An empty result does not always mean the symbol is unknown: yfinance also
    returns one when it is rate-limited, so the message says only that no
    data was found.
    """


def get_price_data(symbol: str, period: str = "6mo") -> pd.DataFrame:
    cleaned_symbol = symbol.strip().upper()
    if not cleaned_symbol:
        raise ValueError("Symbol is required.")

    try:
        data = yf.Ticker(cleaned_symbol).history(
            period=period,
            interval="1d",
            auto_adjust=True,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        # yfinance raises its own exception classes on some paths and plain
        # network errors on others, and the set changes between releases, so
        # translate whatever the call site throws rather than enumerate it.
        logger.warning(
            "market_data_unavailable",
            extra={"symbol": cleaned_symbol, "period": period, "error": str(exc)},
        )
        raise MarketDataUnavailableError(
            f"Market data for {cleaned_symbol} is temporarily unavailable. Try again shortly."
        ) from exc

    if data.empty:
        raise NoPriceDataError(f"No price data found for symbol: {cleaned_symbol}")

    return data
