"""Download the ablation's price data once and cache it as CSV.

    python -I research/download_data.py

Fetches daily bars for every symbol in research/config.py with the same
adjustment the API uses (auto_adjust=True), checks them, and writes
research/data/<SYMBOL>.csv plus research/data/manifest.json with each
file's SHA-256. It refuses to run if any CSV already exists, so the cached
data is never replaced by a later download (yfinance re-adjusts history
after every dividend, so a second download would not be identical).

Prints only row counts and dates, never prices or returns.
"""

import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research.config import (  # noqa: E402
    DATA_DIR,
    FIRST_DAY,
    LAST_DAY,
    MANIFEST_PATH,
    PRICE_COLUMNS,
    SYMBOLS,
)

REQUEST_TIMEOUT_SECONDS = 30


def _fetch(symbol: str) -> pd.DataFrame:
    history = yf.Ticker(symbol).history(
        start=FIRST_DAY.isoformat(),
        # yfinance's end date is exclusive.
        end=(LAST_DAY + timedelta(days=1)).isoformat(),
        interval="1d",
        auto_adjust=True,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if history.empty:
        raise RuntimeError(f"{symbol}: yfinance returned no rows")

    prices = history[PRICE_COLUMNS].copy()
    # Calendar dates, at the resolution read_csv gives them back.
    prices.index = pd.DatetimeIndex(prices.index.date, name="Date").as_unit("us")

    problems = []
    if prices.index.has_duplicates:
        problems.append("duplicate dates")
    if not prices.index.is_monotonic_increasing:
        problems.append("dates out of order")
    if prices[["Open", "Close"]].isna().any().any():
        problems.append("missing Open or Close")
    if (prices[["Open", "Close"]] <= 0).any().any():
        problems.append("non-positive Open or Close")
    if prices.index[0].date() > FIRST_DAY + timedelta(days=4):
        problems.append(f"starts late, on {prices.index[0].date()}")
    if prices.index[-1].date() != LAST_DAY:
        problems.append(f"ends on {prices.index[-1].date()}, not {LAST_DAY}")
    if problems:
        raise RuntimeError(f"{symbol}: " + "; ".join(problems))

    return prices


def _write(symbol: str, prices: pd.DataFrame) -> dict:
    path = DATA_DIR / f"{symbol}.csv"
    # "\n" on every platform; research/data/.gitattributes stops git from
    # converting line endings, so the bytes and their hash survive checkout.
    prices.to_csv(path, lineterminator="\n")

    reread = pd.read_csv(path, index_col="Date", parse_dates=True, float_precision="round_trip")
    pd.testing.assert_frame_equal(reread, prices, check_exact=True, check_freq=False)

    return {
        "file": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "rows": len(prices),
        "first_day": prices.index[0].date().isoformat(),
        "last_day": prices.index[-1].date().isoformat(),
    }


def main() -> int:
    existing = sorted(path.name for path in DATA_DIR.glob("*.csv"))
    if existing:
        print(f"Refusing to download: {DATA_DIR} already holds {', '.join(existing)}")
        return 1

    # Fetch and check everything before writing anything.
    fetched = {}
    for symbol in SYMBOLS:
        fetched[symbol] = _fetch(symbol)
        print(f"{symbol}: {len(fetched[symbol])} rows")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    files = {symbol: _write(symbol, prices) for symbol, prices in fetched.items()}

    manifest = {
        "downloaded_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "source": "yfinance Ticker.history",
        "request": {
            "first_day": FIRST_DAY.isoformat(),
            "last_day": LAST_DAY.isoformat(),
            "interval": "1d",
            "auto_adjust": True,
        },
        "versions": {"yfinance": yf.__version__, "pandas": pd.__version__},
        "files": files,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")

    for symbol, entry in files.items():
        print(f"{symbol}: {entry['first_day']} to {entry['last_day']}, {entry['rows']} rows")
    print(f"Wrote {len(files)} files and {MANIFEST_PATH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
