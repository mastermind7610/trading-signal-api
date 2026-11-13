# TRADING_SIMMS

A paper trading signal and backtesting system built with FastAPI.

> **WARNING: This system is for research and paper trading only. It does not connect to any broker, execute real orders, or manage real money. Do not use it for live trading.**

---

## Purpose

TRADING_SIMMS generates trading signals (BUY / SELL / HOLD) from a 20/50-day moving average crossover filtered by trend, RSI and MACD checks, translates each signal into a position-sizing decision for a given portfolio, and evaluates strategy performance through historical backtesting. It is a backend-only REST API — no frontend, no database, no broker integration.

---

## Architecture

```
main.py                  — FastAPI app, router registration, error handlers, /health
routes/
    signal.py            — POST /signal  (HTTP in/out only)
    backtest.py          — POST /backtest (HTTP in/out only)
    auth.py              — X-API-Key check applied to both routes
schemas/
    common.py            — SymbolRequest: symbol validation shared by both requests
    signal.py            — SignalRequest, SignalResponse
    backtest.py          — BacktestRequest, BacktestResponse
services/
    data.py              — fetches market data via yfinance; raises NoPriceDataError (404) or MarketDataUnavailableError (503)
    features.py          — computes daily returns, moving averages, volatility, trend slope, price position, RSI, MACD
    signal.py            — generates BUY/SELL/HOLD signal with confidence score
    decisions.py         — converts a signal + confidence into a position-sizing decision
    backtest.py          — walk-forward, long-only backtest with next-day fills and trading costs
tests/
    test_signal.py       — unit tests for signal generation (no live data)
    test_decisions.py    — unit tests for position-sizing decisions
    test_backtest.py     — unit tests for backtest engine (no live data)
    test_features.py     — unit tests for feature calculations
    test_backtest_route.py — HTTP-layer tests via TestClient (no live data)
    test_validation.py   — request validation for both endpoints (no live data)
    test_data.py         — unit tests for the data fetch and its error translation (no live data)
    test_api_metadata.py — /health and the generated OpenAPI document
    test_auth.py         — API key check as deployed: 401, 503 when unconfigured, public routes
    conftest.py          — switches the API key check off for every other test
scripts/
    backtest_report.py   — regenerates the Backtest Results table and example responses (needs internet)
requirements.txt         — runtime dependencies, exact pins (what the Docker image installs)
requirements-dev.txt     — the above plus pytest and httpx
Dockerfile               — production image: runtime deps only, explicit copies, non-root user
.github/workflows/deploy.yml — CI: run the tests, then build, push and deploy the image to Azure Container Apps
```

**Data flow:**

- `/signal`: `routes/signal` → `services/data` → `services/features` → `services/signal` → `services/decisions`
- `/backtest`: `routes/backtest` → `services/data` → `services/backtest` (which calls `services/features`, `services/signal` and `services/decisions` internally)

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

For development and running the tests:

```bash
pip install -r requirements-dev.txt
```

`requirements.txt` holds the runtime dependencies with exact version pins and is what the Docker image installs. `requirements-dev.txt` adds pytest and httpx (FastAPI's test client needs it) on top of it.

---

## Running Tests

```bash
python -m pytest -v
```

All 121 tests should pass. Use `python -m pytest`, not bare `pytest` — the `-m` form puts the project root on the import path. No internet connection is required — tests use fake DataFrames and monkeypatched dependencies.

---

## Running the API

```bash
uvicorn main:app --reload
```

The server starts at `http://127.0.0.1:8000`. `/signal` and `/backtest` answer `503` until an API key is configured: see [Authentication](#authentication) for the one-line setup.

---

## Authentication

`/signal` and `/backtest` require an API key in the `X-API-Key` header. `/health`, `/docs` and `/openapi.json` are public.

The server reads the accepted key from the `API_KEY` environment variable. It **fails closed**: if `API_KEY` is not set, both endpoints answer `503` rather than running open. A missing or wrong key gets `401`.

### Running locally with a key

Pick any value for local use and set it before starting the server.

**Windows (PowerShell):**
```powershell
$env:API_KEY = "<your-local-key>"
uvicorn main:app --reload
```

**macOS / Linux:**
```bash
API_KEY="<your-local-key>" uvicorn main:app --reload
```

Then send the same value with each request:

```bash
curl -X POST http://127.0.0.1:8000/signal \
  -H "X-API-Key: <your-local-key>" \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL"}'
```

In Swagger UI, click **Authorize**, enter the key once, and every "Try it out" call carries it. The test suite needs no key: it switches the check off, except for `tests/test_auth.py`, which exercises it as deployed.

### Setting the key on Azure Container Apps

Generate a long random value, store it as a Container Apps secret and expose it to the app as `API_KEY`. Do this once, **before** deploying a version that requires the key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
az containerapp secret set --name trading-simms --resource-group trading-simms-rg --secrets api-key=<value>
az containerapp update --name trading-simms --resource-group trading-simms-rg --set-env-vars API_KEY=secretref:api-key
```

The secret and the variable persist across revisions, so the deploy workflow needs no change and the key never passes through GitHub. To rotate without downtime, set `API_KEY` to `old,new` (comma-separated values are all accepted), move clients to the new key, then set it to `new` alone.

### Rate limiting (out of scope)

There is no rate limiter. An in-process one would count per replica, reset on every deploy and share no state, so it would not stop real abuse. With one authenticated consumer, the response to a misbehaving or leaked key is to rotate it. Each upstream request is bounded by a 10-second timeout. A public deployment should enforce limits at the edge, for example with Azure API Management or Front Door.

---

## Running with Docker

```bash
docker build -t trading-simms .
docker run --rm -p 8000:8000 -e API_KEY="<your-local-key>" trading-simms
```

The image is built on `python:3.13.3-slim`, installs only `requirements.txt` (no test tools), copies only `main.py`, `routes/`, `schemas/` and `services/`, and runs uvicorn as an unprivileged user (`app`, UID 10001). It needs outbound internet access to reach Yahoo Finance.

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check; returns `{"status": "ok", "version": "..."}` |
| POST | `/signal` | Generate a trading signal for a symbol |
| POST | `/backtest` | Run a historical backtest for a symbol |

**Input validation and errors.** `symbol` must be 1 to 12 characters of letters, digits, `.`, `-`, `^` or `=` (Yahoo Finance ticker syntax). Whitespace is trimmed and the symbol upper-cased, so ` aapl ` becomes `AAPL`. `portfolio_value` must be positive and finite. Invalid input returns `422` naming the failing field.

When Yahoo Finance returns no rows for a symbol the API returns `404` with `No price data found for symbol: X`. This also happens when Yahoo rate-limits requests, so it does not always mean the symbol is unknown. When Yahoo Finance cannot be reached or fails, the API returns `503` with a `Retry-After` header. Each request to Yahoo times out after 10 seconds. A missing or wrong API key returns `401`.

---

## Testing with Swagger UI

Start the server, then open `http://127.0.0.1:8000/docs` in your browser. The docs carry a description of each endpoint, example requests and responses, and the error responses (`401`, `404`, `422`, `503`) with their shape. Click **Authorize** and enter your API key before trying `/signal` or `/backtest` (see [Authentication](#authentication)).

### Test /signal

1. Click **POST /signal** → **Try it out**
2. Enter request body (`portfolio_value` is optional and defaults to 10000):
   ```json
   { "symbol": "AAPL", "portfolio_value": 10000 }
   ```
3. Click **Execute**
4. Example response, captured 2026-11-12 (live values change daily):
   ```json
   {
     "symbol": "AAPL",
     "signal": "BUY",
     "confidence": 0.68,
     "macd_line": 3.7935404005651776,
     "signal_line": 3.0583843631302483,
     "histogram": 0.7351560374349293,
     "decision": {
       "position_pct": 0.04,
       "position_value": 400.0
     }
   }
   ```
   Signal will be BUY, SELL, or HOLD depending on current market data. Confidence is between 0.5 and 0.95 and measures how decisive the moving-average crossover is (see [Signal Logic](#signal-logic)). The `decision` block sizes a position from the confidence score: `position_pct` is the fraction of the portfolio to allocate (capped at 10%), and `position_value` is that fraction applied to `portfolio_value`. `macd_line`, `signal_line` and `histogram` are the latest MACD (12/26/9) values; they are `null` when there is not enough history to compute them.

### Test /backtest

1. Click **POST /backtest** → **Try it out**
2. Enter request body (`period` and `trading_cost_pct` are optional):
   ```json
   { "symbol": "AAPL", "period": "5y", "trading_cost_pct": 0.001 }
   ```
   - `period` — how much daily history to test: `6mo`, `1y`, `2y`, `5y` (default) or `10y`.
   - `trading_cost_pct` — commission plus slippage, as a fraction of the amount bought or sold. Default `0.001` (0.1%), maximum `0.05`.
3. Click **Execute**
4. Example response, captured 2026-11-12 with the default 5-year period:
   ```json
   {
     "symbol": "AAPL",
     "buy_signals": 175,
     "sell_signals": 153,
     "hold_signals": 871,
     "cumulative_strategy_return": 0.0029,
     "buy_and_hold_return": 1.0677,
     "sharpe_ratio": 0.102,
     "max_drawdown": -0.008,
     "trades": 177,
     "total_trading_costs": 0.007587,
     "average_exposure": 0.0088
   }
   ```
   Returns are expressed as decimals (0.10 = 10%).

   **How the backtest trades.** It follows `/signal`'s advice the way you could in a real brokerage account:
   - **Long-only.** BUY holds a position sized exactly as `/signal`'s `decision` block (0–10% of the portfolio). SELL and HOLD both mean cash. Nothing is ever shorted.
   - **Next-day fills.** Each signal uses data up to that day's close, and the order fills at the next day's open. The old position is held overnight until then.
   - **Trading costs.** Every change in position size pays `trading_cost_pct` on the amount traded.
   - **Warm-up.** The first ~54 trading days are indicator warm-up (MA50 plus its 5-day slope), when no signal is possible. The backtest starts on the first day a signal can be computed, and buy-and-hold is measured from that same day.

   **Response fields.**
   - `sharpe_ratio` — annualized Sharpe ratio of the daily strategy returns (risk-free rate 0.0; 0.0 when undefined).
   - `max_drawdown` — the largest peak-to-trough fall in portfolio value, as a negative decimal.
   - `trades` — the number of days the position size changed. Each one pays the trading cost.
   - `total_trading_costs` — the sum of all trading costs, as a fraction of the portfolio.
   - `average_exposure` — the average fraction of the portfolio held in the stock.

---

## Signal Logic

| Condition | Signal |
|-----------|--------|
| 20-day MA > 50-day MA | BUY |
| 20-day MA < 50-day MA | SELL |
| 20-day MA == 50-day MA | HOLD |

If data is insufficient (fewer than 50 trading days) or features contain NaN values, the system falls back to HOLD with confidence 0.5.

The base crossover signal is then refined by overrides. Each can only downgrade a signal to HOLD, never upgrade one:

- A **SELL** is downgraded to **HOLD** if the 50-day trend slope is still rising (> 0.01) or price sits well above the MA50 (> 5%).
- A **BUY** is downgraded to **HOLD** if the 50-day trend slope is falling hard (< -0.01).
- A **BUY** is downgraded to **HOLD** if RSI is overbought (> 70).
- A **SELL** is downgraded to **HOLD** if RSI is oversold (< 30).
- A **BUY** is downgraded to **HOLD** if the MACD histogram is negative (momentum disagrees with the bullish crossover).
- A **SELL** is downgraded to **HOLD** if the MACD histogram is positive (momentum disagrees with the bearish crossover).

RSI is a 14-day Relative Strength Index. When it is unavailable (insufficient history), it defaults to a neutral 50 so it never forces an override.

MACD is the standard 12/26/9 Moving Average Convergence Divergence: the MACD line is the 12-day EMA minus the 26-day EMA, the signal line is a 9-day EMA of the MACD line, and the histogram is their difference. `/signal` returns all three. When there is not enough history they are `null` in the response and the histogram defaults to a neutral 0 so it never forces an override.

### Confidence

Confidence measures how decisive the crossover is: the gap between the two moving averages, as a fraction of the 50-day MA, divided by the 20-day volatility of daily returns.

```
strength   = |MA20 - MA50| / MA50 / rolling_volatility
confidence = 0.5 + 0.45 × min(1, strength / 3)
```

No gap gives 0.5. A gap three daily standard deviations wide, or wider, gives the maximum 0.95. Measuring the gap in volatility units makes confidence comparable across symbols: a 2% gap means a lot for an index fund that moves 0.7% a day and little for a stock that moves 3% a day. Example: a 2% gap at 1% daily volatility is a strength of 2, so confidence is 0.5 + 0.45 × 2/3 = 0.80.

The constant 3 was chosen on the same five-year window of SPY, AAPL, MSFT and NVDA that the [Backtest Results](#backtest-results) report. On that window the median BUY day has a strength near 1.7 and the top quarter sits above 3, so a typical BUY lands near 0.75 and a clearly established trend at the cap. It is a scale choice rather than a fitted edge (2 and 4 give the same qualitative results), but it was not chosen out of sample.

**Known limitation:** confidence describes the crossover, not the final signal, so a signal that an override downgraded to HOLD can still report a high confidence (for example HOLD at 0.95) even though its position is zero; a `reason` field naming the override will fix this in a later step.

### Position Sizing

`services/decisions.py` turns each signal into a position-sizing decision:

- **BUY** → confidence is rescaled from its [0.5, 0.95] range to [0, 1] and applied to a maximum allocation of **10%** of the portfolio.
- **SELL / HOLD** → `position_pct = 0.0` (hold nothing, in cash). The system is long-only and never shorts.

`position_value` is `position_pct × portfolio_value`, rounded to cents. Continuing the example above, confidence 0.80 rescales to 0.667, so `position_pct` is 0.0667 and `position_value` is $667.00 on a $10,000 portfolio.

---

## Backtest Results

Generated by `python scripts/backtest_report.py` on 2026-11-12. Long-only backtests on 5 years of daily data, with next-day fills and the default 0.1% trading cost. After indicator warm-up each covers the same 1,199 trading days, from the first signal day on 2022-02-02 to the last close on 2026-11-12:

| Symbol | Strategy Return | Buy-and-Hold Return | Sharpe | Max Drawdown | Avg. Exposure | Trades | BUY / SELL / HOLD days |
|--------|-----------------|---------------------|--------|--------------|---------------|--------|------------------------|
| SPY    | -0.30%          | +76.38%             | -0.21  | -0.59%       | 1.00%         | 204    | 203 / 112 / 884        |
| AAPL   | +0.29%          | +106.77%            | 0.10   | -0.80%       | 0.88%         | 177    | 175 / 153 / 871        |
| MSFT   | -0.72%          | +73.53%             | -0.31  | -1.19%       | 0.56%         | 147    | 127 / 141 / 931        |
| NVDA   | +0.39%          | +561.21%            | 0.07   | -2.12%       | 0.82%         | 174    | 171 / 146 / 882        |

**What the numbers say.** The strategy is in cash on 83 to 89% of days. The six overrides in [Signal Logic](#signal-logic) downgrade most crossovers, so HOLD fires on 73 to 78% of days and SELL (also cash, since the system is long-only) on most of the rest. BUY fires on only 11 to 17% of days. On those days the position averages 5 to 6% of the portfolio, so average exposure over the whole period is about 1% and the strategy's returns are necessarily small: between -0.72% and +0.39%, against buy-and-hold gains of +73.53% to +561.21%.

The small exposure is the consequence of a cautious rule set, not the cause of the underperformance. An earlier version of this backtest (same signals, 100% invested on BUY, 100% short on SELL, no costs, same-day fills) also trailed buy-and-hold on all four symbols: SPY +11.7% vs +77.3%, AAPL +22.0% vs +105.8%, MSFT -35.0% vs +79.0%, NVDA -0.3% vs +720.7%. Over this period a filtered 20/50-day crossover has no edge over simply holding these symbols, all of which trended strongly upward.

What the backtest does show is that the pipeline behaves as documented: positions follow confidence, every change in position pays a cost, and the strategy and its benchmark are measured over the same days. Past results do not guarantee future performance.

---

## Disclaimer

This project is a **paper trading and research tool only**.

- It does not place real orders.
- It does not connect to any brokerage or exchange.
- Past backtest results do not guarantee future performance.
- Use at your own risk for research purposes only.
