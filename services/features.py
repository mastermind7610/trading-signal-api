import pandas as pd


def build_features(price_data: pd.DataFrame) -> pd.DataFrame:
    """
    Takes raw OHLCV price data and returns a DataFrame with computed indicators.
    """
    features = price_data.copy()

    # Daily return
    features["daily_return"] = features["Close"].pct_change(fill_method=None)

    # Moving averages
    features["ma_20"] = features["Close"].rolling(window=20).mean()
    features["ma_50"] = features["Close"].rolling(window=50).mean()

    # Rolling volatility (20-day standard deviation of returns)
    features["rolling_volatility"] = (
        features["Close"].pct_change().rolling(window=20).std()
    )

    # Trend strength: slope of MA50 over last 5 days
    # Positive = rising trend, negative = falling trend
    features["trend_slope"] = features["ma_50"].diff(5) / features["ma_50"].shift(5)

    # Price position: is price above or below MA50?
    # Positive = bullish, negative = bearish
    features["price_position"] = (
        (features["Close"] - features["ma_50"]) / features["ma_50"]
    )

    # Relative Strength Index (14-day)
    # > 70 = overbought, < 30 = oversold
    delta = features["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss
    features["rsi"] = 100 - (100 / (1 + rs))

    return features