# TRADING_SIMMS

A paper trading signal and backtesting system built with FastAPI.

> **WARNING: This system is for research and paper trading only. It does not connect to any broker, execute real orders, or manage real money. Do not use it for live trading.**

---

## Purpose

TRADING_SIMMS generates trading signals (BUY / SELL / HOLD) from a 20/50-day moving average crossover filtered by trend, RSI and MACD checks, translates each signal into a position-sizing decision for a given portfolio, and evaluates strategy performance through historical backtesting. A daily command-line run applies the same rules one trading day at a time and keeps the resulting paper account in MongoDB. It is backend-only — no frontend and no broker integration.

---

## Architecture

```
main.py                  — FastAPI app, router registration, error handlers, /health
routes/
    signal.py            — POST /signal  (HTTP in/out only)
    backtest.py          — POST /backtest (HTTP in/out only)
    ledger.py            — GET /ledger/{symbol}: reads the daily run's ledger from MongoDB
    auth.py              — X-API-Key check applied to every route except /health
schemas/
    common.py            — symbol validation shared by every route: SymbolRequest (body), SymbolPath (URL)
    signal.py            — SignalRequest, SignalResponse
    backtest.py          — BacktestRequest, BacktestResponse
    ledger.py            — LedgerResponse
services/
    data.py              — fetches market data via yfinance; raises NoPriceDataError (404) or MarketDataUnavailableError (503)
    features.py          — computes daily returns, moving averages, volatility, trend slope, price position, RSI, MACD
    signal.py            — generates BUY/SELL/HOLD signal with confidence score
    decisions.py         — converts a signal + confidence into a position-sizing decision
    backtest.py          — walk-forward, long-only backtest with next-day fills and trading costs
pipeline/
    ledger.py            — one day of paper-trading accounting, by the backtest's rules (no I/O)
    repository.py        — where the ledger is kept: the storage interface and an in-memory implementation
    mongo_repository.py  — the ledger in MongoDB; connection string from MONGODB_URI
    daily.py             — the daily run: records each trading day the ledger is missing, once
    cli.py               — `python -m pipeline SYMBOL ...`: fetches prices and runs the daily run
tests/
    test_signal.py       — unit tests for signal generation (no live data)
    test_decisions.py    — unit tests for position-sizing decisions
    test_backtest.py     — unit tests for backtest engine (no live data)
    test_features.py     — unit tests for feature calculations
    test_backtest_route.py — HTTP-layer tests via TestClient (no live data)
    test_ledger_route.py — GET /ledger: entries, symbol validation, 404, 503s, read-only (no database)
    test_validation.py   — request validation for both endpoints (no live data)
    test_data.py         — unit tests for the data fetch and its error translation (no live data)
    test_api_metadata.py — /health and the generated OpenAPI document
    test_auth.py         — API key check as deployed: 401, 503 when unconfigured, public routes
    test_ledger.py       — day-by-day ledger accounting must match run_backtest (no live data)
    test_daily_run.py    — daily run: reruns, holidays and catch-up after missed days (no live data)
    test_repository_contract.py — what any ledger store must do; also run against MongoDB when MONGODB_URI is set
    test_mongo_repository.py — MongoDB documents, connection string and driver failures (no database)
    test_cli.py          — the daily run's command line (no live data, no database)
    ledger_samples.py    — sample prices and ledger entries shared by the ledger tests
    conftest.py          — switches the API key check off for every other test
scripts/
    backtest_report.py   — regenerates the Backtest Results table and example responses (needs internet)
research/                — offline study of the strategy's vetoes; not used by the API or the image
    RESEARCH.md          — pre-registration, method, results and conclusion (see Backtest Results)
    engine.py            — strategy variants with switchable overrides, checked against run_backtest
    run_tuning.py, run_holdout.py — the tuning-window ablation and the one-shot holdout run
    data/, results/      — cached daily prices (with a SHA-256 manifest) and every output
requirements.txt         — runtime dependencies, exact pins (what the Docker image installs)
requirements-dev.txt     — the above plus pytest, httpx and ruff
pyproject.toml           — ruff (lint + import-order) configuration; no packaging metadata
Dockerfile               — production image: runtime deps only, explicit copies, non-root user
.github/workflows/deploy.yml — CI: lint and test every PR into main; on a push to main, also build and push the image and move the container app and the daily-run job to it
```

**Data flow:**

- `/signal`: `routes/signal` → `services/data` → `services/features` → `services/signal` → `services/decisions`
- `/backtest`: `routes/backtest` → `services/data` → `services/backtest` (which calls `services/features`, `services/signal` and `services/decisions` internally)
- `/ledger/{symbol}`: `routes/ledger` → `pipeline/mongo_repository` (written by `python -m pipeline`, never by the API)

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

`requirements.txt` holds the runtime dependencies with exact version pins and is what the Docker image installs. `requirements-dev.txt` adds pytest, httpx (FastAPI's test client needs it) and ruff on top of it.

---

## Running Tests

```bash
python -m pytest -v
```

All 259 tests should pass, and 10 more are reported as skipped. Use `python -m pytest`, not bare `pytest` — the `-m` form puts the project root on the import path. No internet connection is required — tests use fake DataFrames and monkeypatched dependencies.

The 10 skipped tests check the ledger's MongoDB storage against a real database, so they run only when `MONGODB_URI` is set: see [Testing the MongoDB storage](#testing-the-mongodb-storage).

---

## Linting

```bash
python -m ruff check .
```

Ruff enforces pycodestyle, pyflakes, import order, bugbear and pyupgrade rules; its configuration lives in `pyproject.toml`. CI runs this check before the tests, so the same command run locally catches anything the pipeline would reject. Code formatting is left to the author — `ruff format` is not part of the workflow.

---

## Running the API

```bash
uvicorn main:app --reload
```

The server starts at `http://127.0.0.1:8000`. `/signal`, `/backtest` and `/ledger` answer `503` until an API key is configured: see [Authentication](#authentication) for the one-line setup. `/ledger` also needs `MONGODB_URI`: see [Reading the ledger](#reading-the-ledger).

---

## Authentication

`/signal`, `/backtest` and `/ledger` require an API key in the `X-API-Key` header. `/health`, `/docs` and `/openapi.json` are public.

The server reads the accepted key from the `API_KEY` environment variable. It **fails closed**: if `API_KEY` is not set, all three endpoints answer `503` rather than running open. A missing or wrong key gets `401`, and the key is checked before anything else, so `/ledger` reveals nothing about its database to a caller without one.

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

The image is built on `python:3.13.3-slim`, installs only `requirements.txt` (no test tools), copies only `main.py`, `routes/`, `schemas/`, `services/` and `pipeline/`, and runs uvicorn as an unprivileged user (`app`, UID 10001). It needs outbound internet access to reach Yahoo Finance.

The same image runs the [daily paper-trading run](#daily-paper-trading-run) when given that command instead of the default:

```bash
docker run --rm -e MONGODB_URI="<connection-string>" trading-simms python -m pipeline SPY AAPL
```

`paper-ledger SPY AAPL` is the same command. It exists for the [scheduled job on Azure](#running-it-on-a-schedule-in-azure), whose arguments cannot start with a dash.

---

## Deployment

Version 1.1.0 runs on Azure Container Apps (1.0.0 is tagged `v1.0.0`). `/health` reports the deployed version. The interactive docs are public:

**https://trading-simms.livelyflower-a997e4bc.canadacentral.azurecontainerapps.io/docs**

`/health`, `/docs` and `/openapi.json` answer without a key. `/signal` and `/backtest` require an API key, which is not provided.

Deploys are automatic. Every push to `main` runs the lint and test job and, if it passes, builds the image on the GitHub runner, pushes it to Azure Container Registry tagged with the commit SHA, and points the container app and the [daily-run job](#running-it-on-a-schedule-in-azure) at the new image. Pull requests into `main` run the lint and test job only and never deploy. The workflow is `.github/workflows/deploy.yml`; the app's `API_KEY` is set once on Azure, as described in [Setting the key on Azure Container Apps](#setting-the-key-on-azure-container-apps).

**Live timing.** The slowest request the API accepts is a 10-year `/backtest`. Three consecutive runs for AAPL against the deployed app on 2026-11-15 took 3.5 s, 3.0 s and 3.0 s, end to end, including the Yahoo Finance fetch. That is well under the 10-second budget set for it, so the API has no result cache: every request is computed from fresh data. The first request after the app has been idle can take about 20 seconds while the container wakes; requests after that are served at the speeds above.

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check; returns `{"status": "ok", "version": "..."}` |
| POST | `/signal` | Generate a trading signal for a symbol |
| POST | `/backtest` | Run a historical backtest for a symbol |
| GET | `/ledger/{symbol}` | Read the paper-trading ledger the daily run keeps for a symbol (see [Reading the ledger](#reading-the-ledger)) |

**Input validation and errors.** `symbol`, in a request body or in the `/ledger` path, must be 1 to 12 characters of letters, digits, `.`, `-`, `^` or `=` (Yahoo Finance ticker syntax). Whitespace is trimmed and the symbol upper-cased, so ` aapl ` becomes `AAPL`. `portfolio_value` must be positive and finite. Invalid input returns `422` naming the failing field.

When Yahoo Finance returns no rows for a symbol the API returns `404` with `No price data found for symbol: X`. This also happens when Yahoo rate-limits requests, so it does not always mean the symbol is unknown. When Yahoo Finance cannot be reached or fails, the API returns `503` with a `Retry-After` header. Each request to Yahoo times out after 10 seconds. A missing or wrong API key returns `401`.

---

## Testing with Swagger UI

Start the server, then open `http://127.0.0.1:8000/docs` in your browser. The docs carry a description of each endpoint, example requests and responses, and the error responses (`401`, `404`, `422`, `503`) with their shape. Click **Authorize** and enter your API key before trying `/signal`, `/backtest` or `/ledger` (see [Authentication](#authentication)).

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
     "reason": "ma_crossover_bullish",
     "rsi": 57.34488840886845,
     "macd_line": 3.7935404005651776,
     "signal_line": 3.0583843631302483,
     "histogram": 0.7351560374349293,
     "decision": {
       "position_pct": 0.04,
       "position_value": 400.0
     }
   }
   ```
   Signal will be BUY, SELL, or HOLD depending on current market data. Confidence is between 0.5 and 0.95 and measures how decisive the moving-average crossover is (see [Signal Logic](#signal-logic)). `reason` is a machine-readable code for how the signal was reached — the crossover basis, the veto that forced HOLD, or the fallback that did (see [Reason codes](#reason-codes)). The `decision` block sizes a position from the confidence score: `position_pct` is the fraction of the portfolio to allocate (capped at 10%), and `position_value` is that fraction applied to `portfolio_value`. `rsi` is the latest 14-day Relative Strength Index (0–100). `macd_line`, `signal_line` and `histogram` are the latest MACD (12/26/9) values. `rsi` and the MACD fields are `null` when there is not enough history to compute them.

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
   Returns are expressed as decimals (0.10 = 10%). The `sell_signals` and `hold_signals` counts were captured before the SELL overrides were removed in version 1.1.0, so some of those HOLD days would now count as SELL. Every other field is unaffected.

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

A BUY is then checked against three overrides. Each can only downgrade it to HOLD, never upgrade a signal:

- A **BUY** is downgraded to **HOLD** if the 50-day trend slope is falling hard (< -0.01).
- A **BUY** is downgraded to **HOLD** if RSI is overbought (> 70).
- A **BUY** is downgraded to **HOLD** if the MACD histogram is negative (momentum disagrees with the bullish crossover).

A **SELL** is never overridden. The system is long-only, so SELL and HOLD both mean cash, and turning one into the other cannot change a position. Until version 1.1.0, four overrides did exactly that. The [veto ablation study](research/RESEARCH.md) showed they never changed a position, a return or a risk figure, so they were removed (see [Retired reason codes](#retired-reason-codes)).

RSI is a 14-day Relative Strength Index. `/signal` returns its raw value, or `null` when there is too little history to compute it. For the overrides above, an unavailable RSI is treated as a neutral 50 so it never forces an override — that default is internal to the override check and is not what the response reports.

MACD is the standard 12/26/9 Moving Average Convergence Divergence: the MACD line is the 12-day EMA minus the 26-day EMA, the signal line is a 9-day EMA of the MACD line, and the histogram is their difference. `/signal` returns all three. When there is not enough history they are `null` in the response and the histogram defaults to a neutral 0 so it never forces an override.

### Reason codes

Every `/signal` response carries a `reason`: a single machine-readable code for how the signal was reached. Exactly one code is reported.

| `reason` | Meaning |
|----------|---------|
| `ma_crossover_bullish` | BUY — 20-day MA above 50-day MA, no veto |
| `ma_crossover_bearish` | SELL — 20-day MA below 50-day MA, no veto |
| `no_ma_crossover` | HOLD — the moving averages coincide |
| `buy_vetoed_trend_falling` | BUY vetoed — 50-day trend falling hard (< -0.01) |
| `buy_vetoed_overbought` | BUY vetoed — RSI overbought (> 70) |
| `buy_vetoed_macd_bearish` | BUY vetoed — MACD histogram negative |
| `insufficient_price_history` | HOLD — fewer than 50 trading days of prices |
| `missing_feature_columns` | HOLD — a required feature column was absent |
| `insufficient_feature_data` | HOLD — no row had every required feature present |
| `invalid_feature_values` | HOLD — a required feature was null, or MA50 was zero |
| `invalid_confidence` | HOLD — the computed confidence was not finite |

The overrides are checked in the order listed under [Signal Logic](#signal-logic), and only the first one that matches can fire, so a `buy_vetoed_*` code names the single veto responsible. Whenever a veto downgrades a BUY to HOLD, confidence is the HOLD floor of 0.5, not the score the rejected crossover would have earned. A SELL reports the crossover's own confidence.

#### Retired reason codes

These codes were removed in version 1.1.0 (2026-11-22), along with the SELL overrides that produced them. `/signal` no longer returns them. Ledger entries recorded before then still carry them, because a recorded day is never recomputed. Each one marks a bearish crossover reported as HOLD at confidence 0.5. That day was in cash, exactly as a SELL is now.

| `reason` | Meaning |
|----------|---------|
| `sell_vetoed_trend_rising` | SELL reported as HOLD — 50-day trend still rising (> 0.01) |
| `sell_vetoed_price_above_ma50` | SELL reported as HOLD — price well above MA50 (> 5%) |
| `sell_vetoed_oversold` | SELL reported as HOLD — RSI oversold (< 30) |
| `sell_vetoed_macd_bullish` | SELL reported as HOLD — MACD histogram positive |

### Confidence

Confidence measures how decisive the crossover is: the gap between the two moving averages, as a fraction of the 50-day MA, divided by the 20-day volatility of daily returns.

```
strength   = |MA20 - MA50| / MA50 / rolling_volatility
confidence = 0.5 + 0.45 × min(1, strength / 3)
```

No gap gives 0.5. A gap three daily standard deviations wide, or wider, gives the maximum 0.95. Measuring the gap in volatility units makes confidence comparable across symbols: a 2% gap means a lot for an index fund that moves 0.7% a day and little for a stock that moves 3% a day. Example: a 2% gap at 1% daily volatility is a strength of 2, so confidence is 0.5 + 0.45 × 2/3 = 0.80.

The constant 3 was chosen on the same five-year window of SPY, AAPL, MSFT and NVDA that the [Backtest Results](#backtest-results) report. On that window the median BUY day has a strength near 1.7 and the top quarter sits above 3, so a typical BUY lands near 0.75 and a clearly established trend at the cap. It is a scale choice rather than a fitted edge (2 and 4 give the same qualitative results), but it was not chosen out of sample.

Confidence describes the crossover. When a veto downgrades a BUY to HOLD, reporting the crossover's score would be misleading — a zero-position HOLD at 0.95 — so the response instead reports the HOLD floor of 0.5 and the `reason` field names the veto that fired (see [Reason codes](#reason-codes)). A SELL keeps the crossover's score. It says how decisive the bearish crossover is, and the position is cash whatever the score.

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

The BUY / SELL / HOLD days were counted before the four SELL overrides were removed in version 1.1.0, so some of those HOLD days would now count as SELL. Every other column is unaffected: the removal changes no position.

**What the numbers say.** The strategy is in cash on 83 to 89% of days. When the table was generated, seven overrides downgraded most crossovers, so HOLD fired on 73 to 78% of days and SELL (also cash, since the system is long-only) on most of the rest. BUY fires on only 11 to 17% of days. On those days the position averages 5 to 6% of the portfolio, so average exposure over the whole period is about 1% and the strategy's returns are necessarily small: between -0.72% and +0.39%, against buy-and-hold gains of +73.53% to +561.21%.

The small exposure is the consequence of a cautious rule set, not the cause of the underperformance. An earlier version of this backtest (same signals, 100% invested on BUY, 100% short on SELL, no costs, same-day fills) also trailed buy-and-hold on all four symbols: SPY +11.7% vs +77.3%, AAPL +22.0% vs +105.8%, MSFT -35.0% vs +79.0%, NVDA -0.3% vs +720.7%. Over this period a filtered 20/50-day crossover has no edge over simply holding these symbols, all of which trended strongly upward.

[research/RESEARCH.md](research/RESEARCH.md) tests that claim more carefully, in a study pre-registered before any data was downloaded. It covers fifteen years of ten large caps, tunes on 2012 to 2021, and checks the one chosen variant once on 2021 to 2026. No variant of the strategy beats buy-and-hold's Sharpe ratio in either window. The study also found that the four SELL overrides never changed a position, because SELL and HOLD both mean cash (they have since been removed), and that the MACD and overbought vetoes lower the Sharpe ratio rather than raise it.

What the backtest does show is that the pipeline behaves as documented: positions follow confidence, every change in position pays a cost, and the strategy and its benchmark are measured over the same days. Past results do not guarantee future performance.

---

## Daily Paper-Trading Run

`python -m pipeline` keeps a paper account for each symbol, one trading day at a time, by the same rules as the backtest: the signal from one day's close sets the position, the order fills at the next day's open, and every change in position pays the 0.1% trading cost. The backtest replays history in one pass and keeps nothing. The daily run records each day once it is over and keeps the result, the **ledger**, in MongoDB. It places no orders: the account is a calculation.

### Running it

Set `MONGODB_URI` to the connection string of the database that holds the ledger, then name the symbols to update.

**Windows (PowerShell):**
```powershell
$env:MONGODB_URI = "<connection-string>"
python -m pipeline SPY AAPL
```

**macOS / Linux:**
```bash
MONGODB_URI="<connection-string>" python -m pipeline SPY AAPL
```

Output of a first run on 2026-11-16, which opened both accounts on the latest finished trading day:

```
SPY 2026-11-13: SELL (ma_crossover_bearish), position 0.00%, return +0.0000%, equity 10,000.00
AAPL 2026-11-13: BUY (ma_crossover_bullish), position 4.00%, return -0.0229%, equity 9,997.71
```

Running it again straight away records nothing:

```
SPY: up to date, last recorded day 2026-11-13
AAPL: up to date, last recorded day 2026-11-13
```

The exit status is `0` when every symbol is up to date, `1` when any symbol failed, and `2` when the command line is wrong or `MONGODB_URI` is missing or malformed. A symbol that fails is reported and the others still run.

### What a run does

A run compares the ledger with the daily prices and records the trading days the ledger does not have. It never consults a market calendar, and it is safe to run at any time and any number of times:

- **First run for a symbol.** The account opens in cash with 10,000 on the latest finished trading day. Earlier days are used only as history for the signal.
- **Run twice.** The second run finds nothing missing and records nothing.
- **Weekend or holiday.** There is no new price bar, so there is nothing to record.
- **Missed days.** The next run records every missing day in order, with the same result as if it had run on each of them.
- **A day still trading.** While a market is open Yahoo Finance already returns a bar for the day, with the latest price in place of the close. A day is recorded only once its date is over in the exchange's own timezone, because a recorded day is never recomputed. So a US trading day is recorded by the first run after midnight in New York: run the command once a day after that, for example at 06:00 UTC from Tuesday to Saturday, as the [Azure job](#running-it-on-a-schedule-in-azure) does.
- **A gap it cannot fill.** Each run fetches two years of daily prices. If the ledger's last day is older than that, the run stops with an error instead of skipping the days in between.

Two years is far more history than the signal needs. It is fetched because the MACD is an exponential average that never fully forgets its first bar, and the fetch window starts a day later each day. After about 500 bars that first bar's weight is around 2e-17, too small to change a signal, so a day gets the same signal whichever day it is computed on.

### Running it on a schedule in Azure

The daily run is an Azure Container Apps job, `trading-simms-daily-run`, in the same environment as the API and on the same image. It runs `paper-ledger SPY AAPL MSFT NVDA` at 06:00 UTC from Tuesday to Saturday. That is 01:00 in New York in winter and 02:00 in summer, so each weekday's session is over and its date has passed there, and the run records it. A run straight after the 16:00 close would not record that day yet, because a day is recorded only once its date is over in New York. A holiday has no bar, so that morning's run records nothing.

The job reads `MONGODB_URI` from its own secret, `mongodb-uri`: a Container Apps job does not see the API's secrets. It writes the ledger, so it connects as its own database user, `trading-simms-pipeline`, with `readWrite` on `trading_simms`, where the API's user needs only `read`. Each deploy moves the job to the new image along with the API. Until the job exists, the deploy skips that step with a warning.

The job is created once, after a deploy has put an image containing `pipeline/` on the container app. No Atlas CLI is needed: the database user and network access are set in the Atlas web UI, and the connection string is written by hand.

**1. The database user.** In Atlas, under Database Access, add a password user `trading-simms-pipeline` whose only privilege is `readWrite` on the `trading_simms` database. Do not give it a project-wide role such as "Read and write to any database".

**2. The connection string.** Build it by hand from that user:

```
mongodb+srv://trading-simms-pipeline:<password>@<cluster-host>/trading_simms?authSource=admin
```

- `<cluster-host>` is the cluster's address, the part after `@` in the string Atlas shows under Connect → Drivers, for example `cluster0.abcde.mongodb.net`.
- In `<password>`, percent-encode any of `: / ? # [ ] @ %`. A password of letters and digits needs no encoding.
- `/trading_simms` selects the database. `authSource=admin` is there because Atlas keeps its database users in `admin`.
- Leave off the `retryWrites=true&w=majority&appName=...` options Atlas adds to its own string. The driver already retries writes by default, and with one query option the string has no `&`, which `az.cmd` mangles when PowerShell passes it on.

**3. Network access.** Atlas refuses connections from addresses not on its Network Access list, so the list must allow the Container Apps environment's outbound IPs. On the Consumption plan those addresses are not fixed, so for now the list allows `0.0.0.0/0` (any address). The database users' passwords are then the only thing keeping other clients out. Narrowing the list needs a fixed outbound address, for example a workload-profiles environment behind a NAT gateway; that one IP would then replace `0.0.0.0/0`.

**4. The job.** These PowerShell commands read the environment, image and registry from the container app. The connection string from step 2 is typed at a hidden prompt, so it never appears on screen or in the shell history.

```powershell
az login

$rg = "trading-simms-rg"
$job = "trading-simms-daily-run"

# The connection string from step 2
$secure = Read-Host "MONGODB_URI for trading-simms-pipeline" -AsSecureString
$uri = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))

# The API's environment, image and registry
$environment = az containerapp show --name trading-simms --resource-group $rg --query properties.environmentId --output tsv
$image = az containerapp show --name trading-simms --resource-group $rg --query "properties.template.containers[0].image" --output tsv
$registry = $image.Split('/')[0]
$acr = $registry.Split('.')[0]
$acrUser = az acr credential show --name $acr --query username --output tsv
$acrPassword = az acr credential show --name $acr --query "passwords[0].value" --output tsv

az containerapp job create --name $job --resource-group $rg --environment $environment `
  --trigger-type Schedule --cron-expression "0 6 * * 2-6" `
  --replica-timeout 600 --replica-retry-limit 1 --replica-completion-count 1 --parallelism 1 `
  --image $image --cpu 0.5 --memory 1.0Gi `
  --registry-server $registry --registry-username $acrUser --registry-password $acrPassword `
  --secrets "mongodb-uri=$uri" --env-vars "MONGODB_URI=secretref:mongodb-uri" `
  --command "paper-ledger" --args "SPY" "AAPL" "MSFT" "NVDA"

Remove-Variable secure, uri, acrPassword
```

Run it once straight away rather than wait for the schedule, then check how it went:

```powershell
az containerapp job start --name $job --resource-group $rg
az containerapp job execution list --name $job --resource-group $rg --output table
```

An execution fails when the command exits non-zero: `1` if any symbol failed, `2` if `MONGODB_URI` is missing or malformed. A failed execution is retried once. That is safe because a run never records a day twice, and a symbol that still fails is caught up by the next morning's run. If an execution fails on the database, check the Network Access list (step 3) first. To change the symbols, run `az containerapp job update --name $job --resource-group $rg --args "SPY" "QQQ"`. The ledger keeps the days already recorded for symbols that are dropped.

### Where the ledger is kept

`MONGODB_URI` is a standard MongoDB connection string, for example the one MongoDB Atlas gives for a cluster. It contains a password: keep it in the environment or a secret store, never in the repository. The database is the one named in the string's path, or `trading_simms` if it names none, and the collection is `ledger`. The database user needs the `readWrite` role on that database.

There is one document per symbol per trading day. This is the AAPL day from the run above:

```json
{
  "symbol": "AAPL",
  "trade_date": "2026-11-13",
  "signal_date": "2026-11-12",
  "signal": "BUY",
  "confidence": 0.68,
  "reason": "ma_crossover_bullish",
  "prev_close": 354.8800048828125,
  "open_price": 357.9599914550781,
  "close_price": 356.2699890136719,
  "day": {
    "position_before": 0.0,
    "position_after": 0.04,
    "traded_pct": 0.04,
    "traded": true,
    "cost_pct": 0.00004,
    "daily_return": -0.00022884819328959245,
    "equity": 9997.711518067104,
    "position_value": 399.9084607226842,
    "cash": 9597.80305734442
  }
}
```

`signal_date` is the day whose close produced the signal. `trade_date` is the next trading day, when the order filled at the open and the account was valued at the close. Positions and costs are fractions of the account, as in the backtest. `equity`, `position_value` and `cash` describe the account at that day's close.

A unique index on `symbol` and `trade_date`, created by the first write, means two runs that overlap cannot both record the same day. Every database operation is given 10 seconds, and a database that cannot be reached is reported as a failure for that symbol.

### Reading the ledger

`GET /ledger/{symbol}` returns every day the daily run has recorded for a symbol, oldest first. It takes the same `X-API-Key` as the other endpoints and only reads: the ledger is written by `python -m pipeline`, never through the API.

```bash
curl http://127.0.0.1:8000/ledger/AAPL -H "X-API-Key: <your-local-key>"
```

The fields are the stored document's, with the `day` block lifted into each entry:

```json
{
  "symbol": "AAPL",
  "entries": [
    {
      "trade_date": "2026-11-13",
      "signal_date": "2026-11-12",
      "signal": "BUY",
      "confidence": 0.68,
      "reason": "ma_crossover_bullish",
      "prev_close": 354.8800048828125,
      "open_price": 357.9599914550781,
      "close_price": 356.2699890136719,
      "position_before": 0.0,
      "position_after": 0.04,
      "traded_pct": 0.04,
      "traded": true,
      "cost_pct": 0.00004,
      "daily_return": -0.00022884819328959245,
      "equity": 9997.711518067104,
      "position_value": 399.9084607226842,
      "cash": 9597.80305734442
    }
  ]
}
```

Days recorded before version 1.1.0 keep the labels the signal gave them then. A bearish crossover that one of the [retired SELL overrides](#retired-reason-codes) caught is a HOLD with a `sell_vetoed_*` reason at confidence 0.5, where a later day reads SELL with `ma_crossover_bearish`. Both held cash, so their money figures are computed the same way.

The server reads the ledger from the database `MONGODB_URI` points to, so set it alongside `API_KEY` before starting uvicorn or the container. The API only reads, so its database user needs only the `read` role. One MongoDB client is built per server process and reused by every request.

| Status | When |
|--------|------|
| `404` | The daily run has recorded no days for the symbol. |
| `503` | `MONGODB_URI` is not set on the server or is not a valid connection string, or the database cannot be reached within 10 seconds. The last two also send `Retry-After`. Neither the connection string nor the driver's error, which names the database hosts, appears in the response. |

### Testing the MongoDB storage

`tests/test_repository_contract.py` holds the tests every ledger store must pass. They always run against the in-memory store. When `MONGODB_URI` is set they also run against that database; otherwise those runs are skipped. Each test uses its own collection with a random name starting `ledger_test_` and drops it afterwards, so the `ledger` collection is never read or written.

```bash
MONGODB_URI="<connection-string>" python -m pytest tests/test_repository_contract.py -v
```

Any MongoDB will do. A disposable local one:

```bash
docker run --rm -d --name ledger-test-db -p 127.0.0.1:27017:27017 mongo:8
MONGODB_URI="mongodb://127.0.0.1:27017" python -m pytest tests/test_repository_contract.py -v
docker stop ledger-test-db
```

---

## Disclaimer

This project is a **paper trading and research tool only**.

- It does not place real orders.
- It does not connect to any brokerage or exchange.
- Past backtest results do not guarantee future performance.
- Use at your own risk for research purposes only.
