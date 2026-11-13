import pandas as pd
import pytest

from services import data as data_service
from services.data import (
    REQUEST_TIMEOUT_SECONDS,
    MarketDataError,
    MarketDataUnavailableError,
    NoPriceDataError,
    get_price_data,
)


@pytest.fixture
def fake_yfinance(monkeypatch):
    """Replace yfinance.Ticker with a fake and return its recorder.

    Set recorder.frame to control what history() returns, or recorder.error
    to make history() raise. No network access happens.
    """

    class Recorder:
        frame = pd.DataFrame({"Open": [100.0], "Close": [101.0]})
        error = None
        symbols = []
        history_kwargs = []

    class FakeTicker:
        def __init__(self, symbol):
            Recorder.symbols.append(symbol)

        def history(self, **kwargs):
            Recorder.history_kwargs.append(kwargs)
            if Recorder.error is not None:
                raise Recorder.error
            return Recorder.frame

    monkeypatch.setattr(data_service.yf, "Ticker", FakeTicker)
    return Recorder


def test_get_price_data_returns_frame_and_passes_request_options(fake_yfinance):
    result = get_price_data(" aapl ", period="2y")

    assert result is fake_yfinance.frame
    assert fake_yfinance.symbols == ["AAPL"]
    assert fake_yfinance.history_kwargs == [
        {
            "period": "2y",
            "interval": "1d",
            "auto_adjust": True,
            "timeout": REQUEST_TIMEOUT_SECONDS,
        }
    ]


def test_get_price_data_defaults_to_six_months(fake_yfinance):
    get_price_data("AAPL")

    assert fake_yfinance.history_kwargs[0]["period"] == "6mo"


def test_get_price_data_empty_result_is_no_price_data(fake_yfinance):
    fake_yfinance.frame = pd.DataFrame()

    with pytest.raises(NoPriceDataError) as excinfo:
        get_price_data("xyz")

    # Worded as "no data found", not "unknown symbol": yfinance also returns
    # an empty frame when it is rate-limited.
    assert str(excinfo.value) == "No price data found for symbol: XYZ"
    assert isinstance(excinfo.value, MarketDataError)


def test_get_price_data_upstream_error_is_unavailable(fake_yfinance):
    fake_yfinance.error = RuntimeError("boom")

    with pytest.raises(MarketDataUnavailableError) as excinfo:
        get_price_data("AAPL")

    assert "AAPL" in str(excinfo.value)
    assert isinstance(excinfo.value, MarketDataError)
    # The original error is kept as the cause for logs and debugging.
    assert isinstance(excinfo.value.__cause__, RuntimeError)


def test_get_price_data_timeout_is_unavailable(fake_yfinance):
    # Any exception from the call site is translated, not just yfinance's own.
    fake_yfinance.error = TimeoutError("read timed out")

    with pytest.raises(MarketDataUnavailableError):
        get_price_data("AAPL")


def test_get_price_data_rejects_empty_symbol_before_fetching(fake_yfinance):
    with pytest.raises(ValueError, match="Symbol is required"):
        get_price_data("   ")

    assert fake_yfinance.symbols == []
