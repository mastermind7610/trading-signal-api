# Veto ablation: does the strategy beat buy-and-hold?

Question: does the `/signal` strategy have any edge over buy-and-hold, and
which of its vetoes help or hurt?

This file was first committed before any data was downloaded or any result
computed. The sections up to and including "Selection rule" are that
pre-registration and are not edited after results exist; results are
appended below them.

## Pre-registration (fixed 2026-11-17, before any data or results)

### Universe

Ten symbols: SPY, AAPL, MSFT, NVDA (given), plus six large caps chosen now:

| Symbol | Sector |
|--------|--------|
| JPM | Financials |
| JNJ | Health Care |
| XOM | Energy |
| PG | Consumer Staples |
| HD | Consumer Discretionary |
| CAT | Industrials |

Rule for the six: one company from each of six sectors that AAPL, MSFT and
NVDA do not cover, each already a large cap at the start of the window
(November 2011). The second condition limits, but does not remove,
survivorship bias: every name on the list is still trading and still large
today, and NVDA in particular was not a large cap in 2011.

### Data

Daily bars from yfinance for 2011-11-17 to 2026-11-16 inclusive,
split- and dividend-adjusted (`auto_adjust=True`, the same adjustment
`services/data.py` uses). Downloaded once to `research/data/<SYMBOL>.csv`,
with a manifest recording the SHA-256 of each file. Every later script loads
the CSVs and refuses to run if a hash does not match, so every run sees
identical data.

### Split

A day's return belongs to the day it is earned (the order from day t's
close fills at day t+1's open, so the return belongs to t+1).

- Tuning window: return days up to and including 2021-11-16 (the first ten
  years). The first 54 bars are indicator warm-up (MA50 plus its 5-day
  slope), so scoring starts about ten weeks in.
- Holdout: return days from 2021-11-17 to 2026-11-16 (the last five years).
  Indicators there are computed with earlier prices as warm-up, which is
  information a trader would have had. The account starts flat in cash at
  the close of 2021-11-16.

Tuning scripts truncate the data at 2021-11-16 before computing anything.
The holdout script runs once: it refuses to run if its result file already
exists.

### Trading rules (identical to `services/backtest.py`)

- The signal for day t uses data up to day t's close.
- The target position is `make_decision` from `services/decisions.py`: a
  BUY holds 0 to 10% of the account, sized by confidence; SELL and HOLD
  both hold cash. Long only.
- The order fills at day t+1's open. The old position earns the overnight
  move, the new one the open-to-close move.
- Every change in position pays 0.1% of the amount traded.
- Cash earns nothing.

A check script must show that the research engine reproduces
`run_backtest` exactly, metric for metric, for the full strategy on the
tuning data before any variant is run.

### Variants

- **Buy-and-hold**: 100% invested from the first open (one 0.1% entry
  cost), never sold. The benchmark, not a candidate.
- **Bare crossover**: BUY when the 20-day MA is above the 50-day MA, no
  vetoes, same confidence sizing.
- **Full strategy**: the crossover with all overrides, as `/signal` runs
  today.
- **Full minus one**: the full strategy with one override removed.
- **Bare plus one**: the bare crossover with one override added.

The README groups the overrides into six bullets, but the first bullet
holds two checks, so the code has seven:

| Code | Override |
|------|----------|
| `sell_trend_rising` | SELL becomes HOLD if the MA50 5-day slope > 0.01 |
| `buy_trend_falling` | BUY becomes HOLD if the MA50 5-day slope < -0.01 |
| `sell_price_above_ma50` | SELL becomes HOLD if price is > 5% above MA50 |
| `buy_overbought` | BUY becomes HOLD if RSI(14) > 70 |
| `sell_oversold` | SELL becomes HOLD if RSI(14) < 30 |
| `buy_macd_bearish` | BUY becomes HOLD if the MACD histogram < 0 |
| `sell_macd_bullish` | SELL becomes HOLD if the MACD histogram > 0 |

All seven are ablated, so the variant count is 1 + 1 + 7 + 7 = 16 strategy
variants plus the benchmark.

Prediction from reading the code, to be checked against the numbers: the
four SELL overrides cannot change a position, because they only turn a SELL
into a HOLD and both mean cash. If so, "full minus a SELL override" equals
the full strategy and "bare plus a SELL override" equals the bare
crossover, leaving 8 distinct trading rules.

### Metrics

Per variant and symbol, after costs: cumulative return, annualized Sharpe
ratio (daily returns, zero risk-free rate, 252 days), maximum drawdown,
average exposure (mean fraction of the account held), and trade count
(days the position changed). Each is summarized across the ten symbols by
its median.

### Selection rule

Sharpe is the only one of the five metrics that compares a strategy holding
at most 10% with buy-and-hold at 100%: scaling every position by the same
factor (costs included) leaves it unchanged. Return and drawdown are
reported, but they mostly measure exposure here, so selection does not use
them.

- Score of a variant = the median over the ten symbols of (variant Sharpe
  minus buy-and-hold Sharpe) on the tuning window.
- The variant with the highest score is chosen. Ties (equal to four
  decimals) go to the variant with fewer overrides.
- Exactly one variant goes to the holdout, even if its score is not
  positive, so the holdout reports the strategy's best showing; a
  non-positive score is stated as "no in-sample edge".
- The holdout runs the chosen variant and buy-and-hold, nothing else.

The holdout shows an edge only if the chosen variant has a higher Sharpe
than buy-and-hold on at least 8 of the 10 symbols and the median
difference is positive. Eight of ten would be a one-sided sign-test p of
0.055 if the symbols were independent. They are not (all are US large
caps, and SPY holds the other nine), so this bar is lenient.
