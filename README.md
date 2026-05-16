# TRADING_SIMMS

A paper trading signal and backtesting system built with FastAPI.

> **WARNING: This system is for research and paper trading only. It does not connect to any broker, execute real orders, or manage real money. Do not use it for live trading.**

---

## Purpose

TRADING_SIMMS generates trading signals (BUY / SELL / HOLD) based on moving average crossovers and evaluates strategy performance through historical backtesting. It is a backend-only REST API — no frontend, no database, no broker integration.

---

## Architecture

```
main.py                  — FastAPI app, router registration, /health
routes/
    signal.py            — POST /signal  (HTTP in/out only)
    backtest.py          — POST /backtest (HTTP in/out only)
schemas/
    signal.py            — SignalRequest, SignalResponse
    backtest.py          — BacktestRequest, BacktestResponse
services/
    data.py              — fetches market data via yfinance
    features.py          — computes daily returns, moving averages, volatility
    signal.py            — generates BUY/SELL/HOLD signal with confidence score
    backtest.py          — walk-forward backtest, returns cumulative returns
tests/
    test_signal.py       — unit tests for signal generation (no live data)
    test_backtest.py     — unit tests for backtest engine (no live data)
    test_features.py     — unit tests for feature calculations
    test_backtest_route.py — HTTP-layer tests via TestClient (no live data)
```

**Data flow:**

- `/signal`: `routes/signal` → `services/data` → `services/features` → `services/signal`
- `/backtest`: `routes/backtest` → `services/data` → `services/backtest` (which calls `services/features` and `services/signal` internally)

---

## Setup

### 1. Create and activate a virtual environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

---

## Running Tests

```bash
python -m pytest -v
```

All 17 tests should pass. No internet connection is required — tests use fake DataFrames and monkeypatched dependencies.

---

## Running the API

```bash
uvicorn main:app --reload
```

The server starts at `http://127.0.0.1:8000`.

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/signal` | Generate a trading signal for a symbol |
| POST | `/backtest` | Run a historical backtest for a symbol |

---

## Testing with Swagger UI

Start the server, then open `http://127.0.0.1:8000/docs` in your browser.

### Test /signal

1. Click **POST /signal** → **Try it out**
2. Enter request body:
   ```json
   { "symbol": "AAPL" }
   ```
3. Click **Execute**
4. Expected response:
   ```json
   {
     "symbol": "AAPL",
     "signal": "BUY",
     "confidence": 0.72
   }
   ```
   Signal will be BUY, SELL, or HOLD depending on current market data. Confidence is between 0.5 and 0.95.

### Test /backtest

1. Click **POST /backtest** → **Try it out**
2. Enter request body:
   ```json
   { "symbol": "AAPL" }
   ```
3. Click **Execute**
4. Expected response:
   ```json
   {
     "symbol": "AAPL",
     "buy_signals": 42,
     "sell_signals": 18,
     "hold_signals": 6,
     "cumulative_strategy_return": 0.1234,
     "buy_and_hold_return": 0.0987
   }
   ```
   Returns are expressed as decimals (0.10 = 10%). The backtest runs over the last 6 months of daily data using a walk-forward approach.

---

## Signal Logic

| Condition | Signal |
|-----------|--------|
| 20-day MA > 50-day MA | BUY |
| 20-day MA < 50-day MA | SELL |
| 20-day MA == 50-day MA | HOLD |

Confidence is penalized by rolling volatility and capped between 0.5 and 0.95. If data is insufficient (fewer than 50 trading days) or features contain NaN values, the system falls back to HOLD with confidence 0.5.

---

## Disclaimer

This project is a **paper trading and research tool only**.

- It does not place real orders.
- It does not connect to any brokerage or exchange.
- Past backtest results do not guarantee future performance.
- Use at your own risk for research purposes only.
