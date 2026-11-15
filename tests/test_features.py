import pandas as pd
import pytest

from services.features import build_features, compute_macd


def test_daily_return_calculation():
    price_data = pd.DataFrame({"Close": [100.0, 110.0, 121.0]})

    features = build_features(price_data)

    assert pd.isna(features.loc[0, "daily_return"])
    assert features.loc[1, "daily_return"] == pytest.approx(0.10)
    assert features.loc[2, "daily_return"] == pytest.approx(0.10)


def test_ma_20_calculation():
    price_data = pd.DataFrame({"Close": list(range(1, 26))})

    features = build_features(price_data)

    assert pd.isna(features.loc[18, "ma_20"])
    assert features.loc[19, "ma_20"] == pytest.approx(sum(range(1, 21)) / 20)
    assert features.loc[24, "ma_20"] == pytest.approx(sum(range(6, 26)) / 20)


def test_ma_50_calculation():
    price_data = pd.DataFrame({"Close": list(range(1, 56))})

    features = build_features(price_data)

    assert pd.isna(features.loc[48, "ma_50"])
    assert features.loc[49, "ma_50"] == pytest.approx(sum(range(1, 51)) / 50)
    assert features.loc[54, "ma_50"] == pytest.approx(sum(range(6, 56)) / 50)


def test_rolling_volatility_calculation():
    price_data = pd.DataFrame({"Close": list(range(100, 131))})
    expected_returns = price_data["Close"].pct_change(fill_method=None)
    expected_volatility = expected_returns.rolling(window=20).std()

    features = build_features(price_data)

    assert pd.isna(features.loc[19, "rolling_volatility"])
    assert features.loc[20, "rolling_volatility"] == pytest.approx(
        expected_volatility.loc[20]
    )
    assert features.loc[30, "rolling_volatility"] == pytest.approx(
        expected_volatility.loc[30]
    )


def test_rsi_calculation():
    # Strictly rising prices: no losses, so RSI saturates at 100.
    price_data = pd.DataFrame({"Close": list(range(100, 130))})

    features = build_features(price_data)

    # RSI needs 14 price changes, so rows before index 14 are NaN.
    assert pd.isna(features.loc[13, "rsi"])
    assert features.loc[14, "rsi"] == pytest.approx(100.0)
    assert features.loc[29, "rsi"] == pytest.approx(100.0)


def test_macd_calculation():
    price_data = pd.DataFrame({"Close": list(range(100, 160))})

    # Recompute the reference MACD with the same EMA definition.
    close = price_data["Close"]
    expected_macd = (
        close.ewm(span=12, adjust=False).mean()
        - close.ewm(span=26, adjust=False).mean()
    )
    expected_signal = expected_macd.ewm(span=9, adjust=False).mean()
    expected_histogram = expected_macd - expected_signal

    features = build_features(price_data)

    assert features.loc[59, "macd"] == pytest.approx(expected_macd.loc[59])
    assert features.loc[59, "macd_signal"] == pytest.approx(expected_signal.loc[59])
    assert features.loc[59, "macd_histogram"] == pytest.approx(
        expected_histogram.loc[59]
    )


def test_macd_histogram_positive_when_rising():
    # A steady uptrend pushes the fast EMA above the slow EMA and keeps the
    # MACD line above its signal line, so the histogram is positive (bullish).
    price_data = pd.DataFrame({"Close": list(range(100, 160))})

    features = build_features(price_data)

    assert features.loc[59, "macd_histogram"] > 0


def test_macd_histogram_negative_when_falling():
    # A steady downtrend drags the MACD line below its signal line, so the
    # histogram turns negative (bearish momentum).
    price_data = pd.DataFrame({"Close": list(range(160, 100, -1))})

    features = build_features(price_data)

    assert features.loc[59, "macd_histogram"] < 0


def test_compute_macd_returns_line_signal_histogram():
    # On a populated row all three series agree with histogram = line - signal.
    close = pd.Series(range(100, 160), dtype=float)

    macd_line, signal_line, histogram = compute_macd(close)

    expected_line = (
        close.ewm(span=12, adjust=False).mean()
        - close.ewm(span=26, adjust=False).mean()
    )
    expected_signal = expected_line.ewm(span=9, adjust=False).mean()

    assert macd_line.iloc[-1] == pytest.approx(expected_line.iloc[-1])
    assert signal_line.iloc[-1] == pytest.approx(expected_signal.iloc[-1])
    assert histogram.iloc[-1] == pytest.approx(
        macd_line.iloc[-1] - signal_line.iloc[-1]
    )


def test_compute_macd_is_nan_safe_for_thin_history():
    # Fewer rows than the 26-period slow EMA: like the RSI rolling window on
    # thin data, MACD is NaN rather than a misleading EMA seed.
    close = pd.Series(range(10), dtype=float)

    macd_line, signal_line, histogram = compute_macd(close)

    assert macd_line.isna().all()
    assert signal_line.isna().all()
    assert histogram.isna().all()


def test_compute_macd_signal_needs_more_history_than_line():
    # Enough rows for the slow EMA (>= 26) but not yet the signal EMA: the MACD
    # line is populated while the signal line and histogram stay NaN.
    close = pd.Series(range(30), dtype=float)

    macd_line, signal_line, histogram = compute_macd(close)

    assert not pd.isna(macd_line.iloc[-1])
    assert pd.isna(signal_line.iloc[-1])
    assert pd.isna(histogram.iloc[-1])
