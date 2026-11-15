import pandas as pd


def compute_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Compute the MACD line, signal line, and histogram for a close-price series.

        macd_line   = EMA(fast) - EMA(slow)
        signal_line = EMA(signal) of the macd_line
        histogram   = macd_line - signal_line

    NaN-safe for thin history, mirroring how the RSI feature's rolling window
    yields NaN until it has enough data: an EMA seeded on only a handful of
    points is misleading, so rows without enough history are returned as NaN
    rather than a noisy seed value. The MACD line needs the slow span; the
    signal line (and therefore the histogram) needs the slow span plus the
    signal span on top of it.
    """
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line

    # Mask thin-history rows only after the full recursion has run, so the
    # populated rows keep their exact values.
    observations = close.notna().cumsum()
    enough_for_macd = observations >= slow
    enough_for_signal = observations >= slow + signal - 1

    macd_line = macd_line.where(enough_for_macd)
    signal_line = signal_line.where(enough_for_signal)
    histogram = histogram.where(enough_for_signal)

    return macd_line, signal_line, histogram


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

    # Moving Average Convergence Divergence (MACD, 12/26/9)
    # histogram > 0 = bullish momentum, < 0 = bearish momentum.
    macd_line, signal_line, histogram = compute_macd(features["Close"])
    features["macd"] = macd_line
    features["macd_signal"] = signal_line
    features["macd_histogram"] = histogram

    return features
