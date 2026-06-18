import pandas as pd
import pytest

from services.features import build_features


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