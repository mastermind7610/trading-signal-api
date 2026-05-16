import pandas as pd


def build_features(price_data: pd.DataFrame) -> pd.DataFrame:
    """
    Takes raw OHLCV price data and returns a DataFrame with computed indicators.
    """
    features = price_data.copy()

    # Moving averages
    features["ma_20"] = features["Close"].rolling(window=20).mean()
    features["ma_50"] = features["Close"].rolling(window=50).mean()

    # Rolling volatility (20-day standard deviation of returns)
    features["rolling_volatility"] = (
        features["Close"].pct_change().rolling(window=20).std()
    )

    return features