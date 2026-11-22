"""Settings for the veto ablation, as pre-registered in research/RESEARCH.md."""

from datetime import date
from pathlib import Path

SYMBOLS = ("SPY", "AAPL", "MSFT", "NVDA", "JPM", "JNJ", "XOM", "PG", "HD", "CAT")

# Fifteen years of daily bars, both ends inclusive.
FIRST_DAY = date(2011, 11, 17)
LAST_DAY = date(2026, 11, 16)

# A return belongs to the day it is earned. Tuning scores return days up to
# and including TUNING_LAST_DAY; the holdout scores the days after it.
TUNING_LAST_DAY = date(2021, 11, 16)

TRADING_COST_PCT = 0.001

RESEARCH_DIR = Path(__file__).resolve().parent
DATA_DIR = RESEARCH_DIR / "data"
RESULTS_DIR = RESEARCH_DIR / "results"
MANIFEST_PATH = DATA_DIR / "manifest.json"

PRICE_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]
