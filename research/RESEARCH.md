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

---

Everything below was added after the pre-registration, in the order it
happened. Nothing above this line was changed.

## How the run went (2026-11-21)

- **Rebase.** Before the tuning run, the branch was rebased onto `main`
  (9555baa), which had gained the paper-trading ledger and its docs. The
  three earlier research commits kept their content and order.
  `services/` is identical in the old and new bases, and the engine check
  was rerun on the new base.
- **Engine check.** `research/verify_engine.py` passed on all ten symbols.
  On each of the 2,461 tuning signal days, the full strategy's signal and
  position equal production's. Its return, Sharpe, drawdown, exposure,
  trades, costs and signal counts equal `run_backtest`'s. Return days run
  from 2012-02-08 to 2021-11-16.
- **Data.** Every load was checked against the manifest's SHA-256.
- **Deviations from the pre-registration.** None.

## Tuning results (2012-02-08 to 2021-11-16)

Produced by `research/run_tuning.py`. The full output is in
`research/results/` (`tuning_per_symbol.csv`, `tuning_summary.csv`,
`tuning_overrides.csv`, `selection.json`).

### Every variant (medians over the ten symbols)

Score is the median of (variant Sharpe minus buy-and-hold Sharpe). Beats
B&H counts the symbols on which the variant's Sharpe is higher.

| Variant | Overrides | Return | Sharpe | Max drawdown | Exposure | Trades | Score | Beats B&H | Same positions as |
|---|---|---|---|---|---|---|---|---|---|
| `buy_and_hold` | 0 | +391.12% | 0.894 | -41.67% | 100.00% | 1 | +0.0000 | 0/10 |  |
| `bare` | 0 | +6.45% | 0.573 | -2.43% | 4.67% | 965 | -0.2492 | 0/10 | `bare` plus any SELL override |
| `full` | 7 | +0.82% | 0.228 | -1.71% | 0.86% | 410 | -0.7249 | 1/10 | `full` minus any SELL override |
| `full_minus_sell_trend_rising` | 6 | +0.82% | 0.228 | -1.71% | 0.86% | 410 | -0.7249 | 1/10 | `full` |
| `full_minus_buy_trend_falling` | 6 | +0.80% | 0.208 | -1.66% | 0.87% | 414 | -0.7277 | 1/10 |  |
| `full_minus_sell_price_above_ma50` | 6 | +0.82% | 0.228 | -1.71% | 0.86% | 410 | -0.7249 | 1/10 | `full` |
| `full_minus_buy_overbought` | 6 | +1.05% | 0.179 | -1.82% | 2.01% | 590 | -0.6682 | 0/10 |  |
| `full_minus_sell_oversold` | 6 | +0.82% | 0.228 | -1.71% | 0.86% | 410 | -0.7249 | 1/10 | `full` |
| `full_minus_buy_macd_bearish` | 6 | +3.36% | 0.375 | -2.26% | 3.32% | 882 | -0.4038 | 1/10 |  |
| `full_minus_sell_macd_bullish` | 6 | +0.82% | 0.228 | -1.71% | 0.86% | 410 | -0.7249 | 1/10 | `full` |
| `bare_plus_sell_trend_rising` | 1 | +6.45% | 0.573 | -2.43% | 4.67% | 965 | -0.2492 | 0/10 | `bare` |
| `bare_plus_buy_trend_falling` | 1 | +6.37% | 0.564 | -2.43% | 4.66% | 962 | -0.2580 | 0/10 |  |
| `bare_plus_sell_price_above_ma50` | 1 | +6.45% | 0.573 | -2.43% | 4.67% | 965 | -0.2492 | 0/10 | `bare` |
| `bare_plus_buy_overbought` | 1 | +3.43% | 0.378 | -2.26% | 3.32% | 884 | -0.3971 | 1/10 |  |
| `bare_plus_sell_oversold` | 1 | +6.45% | 0.573 | -2.43% | 4.67% | 965 | -0.2492 | 0/10 | `bare` |
| `bare_plus_buy_macd_bearish` | 1 | +0.97% | 0.168 | -1.82% | 2.02% | 598 | -0.6651 | 0/10 |  |
| `bare_plus_sell_macd_bullish` | 1 | +6.45% | 0.573 | -2.43% | 4.67% | 965 | -0.2492 | 0/10 | `bare` |

### Sharpe ratio per symbol (one column per distinct trading rule)

| Symbol | B&H | bare | full | full − trend_falling | full − overbought | full − macd_bearish | bare + trend_falling | bare + overbought | bare + macd_bearish |
|---|---|---|---|---|---|---|---|---|---|
| SPY | 0.987 | 0.720 | -0.433 | -0.396 | -0.173 | 0.577 | 0.709 | 0.590 | -0.152 |
| AAPL | 0.994 | 0.822 | 0.258 | 0.287 | 0.806 | 0.278 | 0.813 | 0.288 | 0.821 |
| MSFT | 1.177 | 0.779 | 0.000 | 0.000 | 0.027 | 0.749 | 0.779 | 0.749 | 0.027 |
| NVDA | 1.324 | 0.925 | 0.651 | 0.652 | 0.456 | 0.927 | 0.925 | 0.928 | 0.456 |
| JPM | 0.800 | 0.576 | 0.603 | 0.590 | 0.371 | 0.627 | 0.562 | 0.642 | 0.363 |
| JNJ | 0.796 | 0.186 | 0.231 | 0.231 | 0.235 | 0.066 | 0.186 | 0.066 | 0.235 |
| XOM | 0.175 | 0.167 | 0.263 | 0.185 | 0.093 | 0.257 | 0.144 | 0.280 | 0.043 |
| PG | 0.751 | 0.520 | -0.430 | -0.430 | -0.239 | 0.456 | 0.520 | 0.456 | -0.239 |
| HD | 1.188 | 0.570 | 0.224 | 0.237 | 0.412 | 0.294 | 0.566 | 0.300 | 0.418 |
| CAT | 0.460 | 0.286 | -0.255 | -0.289 | 0.122 | 0.074 | 0.259 | 0.106 | 0.101 |

### What each override does

Blocks is the share of that side's crossover days on which the
override's condition holds, pooled over symbols. The Sharpe changes are
medians over the ten symbols; up / down counts the symbols where the
Sharpe rose or fell.

| Override | Side | Blocks | Removing it from full: median ΔSharpe | up / down | Adding it to bare: median ΔSharpe | up / down |
|---|---|---|---|---|---|---|
| `sell_trend_rising` | SELL | 0.9% | +0.0000 | 0 / 0 | +0.0000 | 0 / 0 |
| `buy_trend_falling` | BUY | 0.5% | +0.0000 | 4 / 3 | -0.0061 | 0 / 7 |
| `sell_price_above_ma50` | SELL | 2.0% | +0.0000 | 0 / 0 | +0.0000 | 0 / 0 |
| `buy_overbought` | BUY | 25.2% | +0.1070 | 7 / 3 | -0.0920 | 3 / 7 |
| `sell_oversold` | SELL | 13.1% | +0.0000 | 0 / 0 | +0.0000 | 0 / 0 |
| `buy_macd_bearish` | BUY | 53.6% | +0.1731 | 8 / 2 | -0.1993 | 1 / 9 |
| `sell_macd_bullish` | SELL | 60.6% | +0.0000 | 0 / 0 | +0.0000 | 0 / 0 |

### What the tuning window says

1. **The four SELL overrides do nothing.** As predicted from the code,
   removing any of them from the full strategy, or adding any of them to
   the bare crossover, leaves every position on every day unchanged. They
   turn SELL into HOLD, and in a long-only strategy both mean cash. So the
   16 variants are 8 distinct trading rules.
2. **No variant beats buy-and-hold.** Buy-and-hold's median Sharpe is
   0.894. The best variant, the bare crossover, has 0.573 and beats
   buy-and-hold on none of the ten symbols. No variant beats it on more
   than one symbol, and that symbol is always XOM, whose buy-and-hold
   Sharpe over these years was only 0.175.
3. **The two BUY vetoes that fire often both hurt.**
   - The MACD veto blocks 54% of BUY days. Removing it from the full
     strategy raises the median Sharpe by 0.17 (up on 8 of 10 symbols);
     adding it alone to the bare crossover lowers it by 0.20 (down on 9).
   - The overbought veto blocks 25%. Removing it raises the median Sharpe
     by 0.11 (up on 7); adding it lowers it by 0.09 (down on 7).
   - The falling-trend veto blocks 0.5% of BUY days and changes little.
   - With every override on, the strategy as deployed has a median Sharpe
     of 0.228, near the bottom of the table: the vetoes remove most of
     the bare crossover's (already insufficient) risk-adjusted return.
4. **Return and drawdown mostly measure exposure.** The bare crossover
   holds 4.7% of the account on a median day and the full strategy 0.9%,
   against buy-and-hold's 100%. That is why their returns (+6.45%,
   +0.82%) and drawdowns (-2.43%, -1.71%) are so far from buy-and-hold's
   (+391%, -41.7%). Sharpe is the comparison that does not depend on
   exposure.

## The choice (written and committed before the holdout was touched)

**Chosen variant: `bare`, the 20/50-day crossover with no overrides,**
sized by confidence exactly as `/signal` sizes a BUY.

Why: the pre-registered rule ranks variants by the median of (variant
Sharpe minus buy-and-hold Sharpe), and `bare` has the highest score,
-0.2492. Four other variants share that score, but they are `bare` plus a
SELL override, which hold identical positions, and they lose the tie on
number of overrides.

The score is negative and `bare` beats buy-and-hold on 0 of 10 symbols,
so by the pre-registered wording this is **no in-sample edge**. It still
goes to the holdout, as pre-registered, because the holdout is meant to
report the strategy's best showing out of sample. A negative score here
already answers the first question for the tuning window, so the holdout
cannot rescue an edge. It can only show whether this ranking holds up.

Before the holdout run, the expectation is that `bare` again has a lower
Sharpe than buy-and-hold on most symbols.

The holdout script runs only `bare` and buy-and-hold. It refuses to run
if anything under `research/` is uncommitted, so this choice is committed
first, and it refuses to run a second time.

## Holdout result (2021-11-17 to 2026-11-16, run once)

`research/run_holdout.py` ran once, at commit 70ea194, after the choice
above was committed. It scored 1,254 return days per symbol. The account
started flat at the close of 2021-11-16, and the indicators were warmed
up on earlier prices. The output is in `research/results/holdout.json`
and `holdout_per_symbol.csv`.

| Symbol | B&H return | B&H Sharpe | B&H max DD | `bare` return | `bare` Sharpe | `bare` max DD | `bare` exposure | `bare` trades | ΔSharpe |
|---|---|---|---|---|---|---|---|---|---|
| SPY | +69.09% | 0.694 | -24.57% | +1.27% | 0.313 | -2.16% | 4.65% | 482 | -0.381 |
| AAPL | +143.99% | 0.777 | -33.17% | +3.64% | 0.496 | -2.18% | 4.19% | 391 | -0.281 |
| MSFT | +60.45% | 0.475 | -36.93% | +1.57% | 0.260 | -2.51% | 3.59% | 458 | -0.216 |
| NVDA | +438.14% | 0.909 | -66.12% | +11.94% | 0.810 | -4.43% | 4.15% | 425 | -0.099 |
| JPM | +132.73% | 0.816 | -38.06% | +1.82% | 0.302 | -1.79% | 4.12% | 451 | -0.514 |
| JNJ | +99.49% | 0.857 | -18.45% | +2.78% | 0.566 | -1.37% | 3.86% | 454 | -0.292 |
| XOM | +209.13% | 0.984 | -20.54% | +0.14% | 0.025 | -3.95% | 3.72% | 534 | -0.959 |
| PG | +34.14% | 0.411 | -23.76% | -1.53% | -0.366 | -3.49% | 3.05% | 461 | -0.777 |
| HD | +1.19% | 0.135 | -34.56% | -0.05% | -0.005 | -2.98% | 3.32% | 412 | -0.139 |
| CAT | +202.92% | 0.845 | -47.27% | +9.02% | 0.936 | -1.98% | 4.33% | 397 | +0.091 |
| **Median** | +116.11% | 0.797 | -33.87% | +1.69% | 0.308 | -2.34% | 3.99% | 452 | -0.286 |

`bare` has a higher Sharpe than buy-and-hold on 1 of the 10 symbols
(CAT), and the median difference is -0.286. The pre-registered test needs
at least 8 of 10 and a positive median. **Result: no edge.**

## How much was tried

The holdout number is not the best of many tries. Here is the full
count:

- **Tuning window:** 16 strategy variants plus buy-and-hold, on 10
  symbols, is 170 backtests. The 16 variants are 8 distinct trading
  rules, because the four SELL overrides never change a position.
- **Holdout:** 1 variant plus buy-and-hold, on 10 symbols, is 20
  backtests, run once.
- **Not tuned:** no thresholds, moving-average lengths or sizing
  constants were changed. Only the overrides were switched on and off,
  which kept the number of trials small.

`bare` was the best of 8 distinct rules on the tuning window, so its
tuning score (-0.249) carries the usual best-of-many optimism. The
holdout score (-0.286) is the unbiased estimate for that one choice. It is
slightly worse, as expected, and points the same way.

## Conclusion

**The strategy has no edge over buy-and-hold on this data, in either
window, with or without its vetoes.**

- **Edge over buy-and-hold: none.**
  - On the tuning years (2012 to 2021), no variant has a higher Sharpe
    than buy-and-hold on more than 1 of 10 symbols. The best one, the
    bare crossover, has a median Sharpe 0.25 lower.
  - On the five holdout years (2021 to 2026), run once, the same rule is
    0.29 lower and beats buy-and-hold only on CAT.
  - The crossover earns a positive Sharpe on most symbols, about 0.3 to
    0.6 at the median, because it is long a rising market part of the
    time. Holding the stock throughout did better on risk-adjusted terms
    as well as raw ones.
- **The four SELL overrides do nothing.** In a long-only strategy SELL
  and HOLD both mean cash, so turning one into the other never changes a
  position. Removing them would change no position, return or risk
  figure. It would change only how `/signal` labels those days: SELL
  instead of HOLD, with that signal's reason code and confidence.
- **The two BUY vetoes that matter make it worse.**
  - The MACD veto blocks about half of BUY days and the overbought veto
    about a quarter.
  - On the tuning window, removing either one raised the median Sharpe
    (by 0.17 and 0.11), and adding either one to the bare crossover
    lowered it (by 0.20 and 0.09).
  - The falling-trend veto almost never fires (0.5% of BUY days) and
    makes no measurable difference.
  - The strategy as deployed has a median tuning Sharpe of 0.23, against
    0.57 for the bare crossover.
  - These veto comparisons are in-sample only. The holdout tested one
    rule, by design, so it confirms nothing about the vetoes.
- **What it would take to claim an edge.** Neither removing vetoes nor
  keeping them gets close. The best rule tried is already 0.25 to 0.29 of
  Sharpe behind buy-and-hold, and the pre-registered test was lenient.

For the project, this supports the README's existing statement that the
filtered crossover has no edge over holding these symbols. It also adds
that the filters reduce risk-adjusted return rather than improve it.
`services/` was not changed: what to do with the vetoes on `/signal` is
a product decision, not something this study settles.

## Limitations

- **Survivorship.** The ten symbols were chosen in 2026 and are all
  still large. That flatters buy-and-hold more than the strategy, which
  is mostly in cash, so it is a reason for caution about the size of the
  gap, not its direction.
- **Correlated symbols.** All ten are US large caps, and SPY holds the
  other nine. The ten results are not ten independent tests.
- **Cash earns nothing.** The engine follows `run_backtest`, where cash
  earns 0. For much of 2023 to 2025, T-bills paid 4 to 5%. A strategy 96% in cash
  would have earned that in practice, but so would any cash alternative.
  The Sharpe comparison uses a zero risk-free rate for both sides.
- **The holdout years were not unseen by the project.** The README's
  5-year backtests (late 2021 to 2026) and the confidence constant
  (`FULL_CONFIDENCE_STRENGTH = 3`, chosen on 5 years of SPY, AAPL, MSFT
  and NVDA) both used data that overlaps the holdout. The holdout is
  untouched by this study's selection but not by the strategy's design.
  That bias favours the strategy, and the result is still no edge.
- **One split and one cost level.** There is a single 10/5-year split
  and a 0.1% cost. With positions of at most 10%, costs are a small part
  of the result.
- **Untested variants.** Only the sizing `/signal` uses (0 to 10% by
  confidence) was tested. Unit-sized or other variants were not
  pre-registered and were not run.
