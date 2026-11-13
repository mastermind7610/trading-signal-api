# TRADING_SIMMS

A paper trading signal and backtesting system built with FastAPI.

> **WARNING: This system is for research and paper trading only. It does not connect to any broker, execute real orders, or manage real money. Do not use it for live trading.**

---

## Purpose

TRADING_SIMMS generates trading signals (BUY / SELL / HOLD) based on moving average crossovers, translates each signal into a position-sizing decision for a given portfolio, and evaluates strategy performance through historical backtesting. It is a backend-only REST API — no frontend, no database, no broker integration.

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
    features.py          — computes daily returns, moving averages, volatility, trend slope, price position, RSI
    signal.py            — generates BUY/SELL/HOLD signal with confidence score
    decisions.py         — converts a signal + confidence into a position-sizing decision
    backtest.py          — walk-forward, long-only backtest with next-day fills and trading costs
tests/
    test_signal.py       — unit tests for signal generation (no live data)
    test_decisions.py    — unit tests for position-sizing decisions
    test_backtest.py     — unit tests for backtest engine (no live data)
    test_features.py     — unit tests for feature calculations
    test_backtest_route.py — HTTP-layer tests via TestClient (no live data)
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

```bash
pip install -r requirements.txt
```

---

## Running Tests

```bash
python -m pytest -v
```

All 51 tests should pass. Use `python -m pytest`, not bare `pytest` — the `-m` form puts the project root on the import path. No internet connection is required — tests use fake DataFrames and monkeypatched dependencies.

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
2. Enter request body (`portfolio_value` is optional and defaults to 10000):
   ```json
   { "symbol": "AAPL", "portfolio_value": 10000 }
   ```
3. Click **Execute**
4. Expected response:
   ```json
   {
     "symbol": "AAPL",
     "signal": "BUY",
     "confidence": 0.72,
     "decision": {
       "position_pct": 0.0489,
       "position_value": 489.0
     }
   }
   ```
   Signal will be BUY, SELL, or HOLD depending on current market data. Confidence is between 0.5 and 0.95. The `decision` block sizes a position from the confidence score: `position_pct` is the fraction of the portfolio to allocate (capped at 10%), and `position_value` is that fraction applied to `portfolio_value`.

### Test /backtest

1. Click **POST /backtest** → **Try it out**
2. Enter request body (`period` and `trading_cost_pct` are optional):
   ```json
   { "symbol": "AAPL", "period": "5y", "trading_cost_pct": 0.001 }
   ```
   - `period` — how much daily history to test: `6mo`, `1y`, `2y`, `5y` (default) or `10y`.
   - `trading_cost_pct` — commission plus slippage, as a fraction of the amount bought or sold. Default `0.001` (0.1%), maximum `0.05`.
3. Click **Execute**
4. Expected response:
   ```json
   {
     "symbol": "AAPL",
     "buy_signals": 174,
     "sell_signals": 154,
     "hold_signals": 870,
     "cumulative_strategy_return": -0.0004,
     "buy_and_hold_return": 1.0578,
     "sharpe_ratio": -0.19,
     "max_drawdown": -0.0009,
     "trades": 95,
     "total_trading_costs": 0.000537,
     "average_exposure": 0.0006
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

Confidence is penalized by rolling volatility and capped between 0.5 and 0.95. If data is insufficient (fewer than 50 trading days) or features contain NaN values, the system falls back to HOLD with confidence 0.5.

The base crossover signal is then refined by trend-aware overrides:

- A **SELL** is downgraded to **HOLD** if the 50-day trend slope is still rising (> 0.01) or price sits well above the MA50 (> 5%).
- A **BUY** is downgraded to **HOLD** if the 50-day trend slope is falling hard (< -0.01).
- A **BUY** is downgraded to **HOLD** if RSI is overbought (> 70).
- A **SELL** is downgraded to **HOLD** if RSI is oversold (< 30).

RSI is a 14-day Relative Strength Index. When it is unavailable (insufficient history), it defaults to a neutral 50 so it never forces an override.

### Position Sizing

`services/decisions.py` turns each signal into a position-sizing decision:

- **BUY** → confidence is rescaled from its [0.5, 0.95] range to [0, 1] and applied to a maximum allocation of **10%** of the portfolio.
- **SELL / HOLD** → `position_pct = 0.0` (hold nothing, in cash). The system is long-only and never shorts.

`position_value` is `position_pct × portfolio_value`, rounded to cents.

---

## Backtest Results

Long-only backtests on 5 years of daily data (2021-11-10 to 2026-11-09), with next-day fills and the default 0.1% trading cost. After indicator warm-up, each covers 1,198 trading days:

| Symbol | Strategy Return | Buy-and-Hold Return | Sharpe | Max Drawdown | Avg. Exposure | Trades | BUY / SELL / HOLD days |
|--------|-----------------|---------------------|--------|--------------|---------------|--------|------------------------|
| SPY    | -0.03%          | +77.26%             | -0.42  | -0.03%       | 0.03%         | 87     | 203 / 111 / 884        |
| AAPL   | -0.04%          | +105.78%            | -0.19  | -0.09%       | 0.06%         | 95     | 174 / 154 / 870        |
| MSFT   | -0.08%          | +79.03%             | -0.44  | -0.12%       | 0.03%         | 70     | 126 / 142 / 930        |
| NVDA   | -0.02%          | +720.66%            | -0.02  | -0.43%       | 0.12%         | 102    | 171 / 147 / 880        |

The strategy lost a little money on every symbol while buy-and-hold gained 77–721%. The main reason is position sizing. Confidence rarely rises much above its 0.5 floor, so BUY positions are a tiny fraction of the 10% maximum, and on average less than 0.15% of the portfolio is ever invested. Before trading costs those small positions roughly broke even, and costs turned that into a small loss on every symbol.

An earlier version of this backtest (same signals, 100% invested on BUY, 100% short on SELL, no costs, same-day fills) also trailed buy-and-hold on all four symbols: SPY +11.7% vs +77.3%, AAPL +22.0% vs +105.8%, MSFT -35.0% vs +79.0%, NVDA -0.3% vs +720.7%. So larger positions alone would not fix it: the signals themselves have not beaten buy-and-hold either.

Past results do not guarantee future performance.

---

## Disclaimer

This project is a **paper trading and research tool only**.

- It does not place real orders.
- It does not connect to any brokerage or exchange.
- Past backtest results do not guarantee future performance.
- Use at your own risk for research purposes only.
