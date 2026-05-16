import pandas as pd
import yfinance as yf


def get_price_data(symbol: str) -> pd.DataFrame:
    cleaned_symbol = symbol.strip().upper()
    if not cleaned_symbol:
        raise ValueError("Symbol is required.")

    data = yf.Ticker(cleaned_symbol).history(
        period="6mo",
        interval="1d",
        auto_adjust=True,
    )

    if data.empty:
        raise ValueError(f"No price data found for symbol: {cleaned_symbol}")

    return data
