### Every variant, tuning window (medians over the ten symbols)

Score = median of (variant Sharpe minus buy-and-hold Sharpe). Beats B&H = symbols on which the variant's Sharpe is higher.

| Variant | Overrides | Return | Sharpe | Max drawdown | Exposure | Trades | Score | Beats B&H | Same positions as |
|---|---|---|---|---|---|---|---|---|---|
| `buy_and_hold` | 0 | +391.12% | 0.894 | -41.67% | 100.00% | 1 | +0.0000 | 0/10 |  |
| `bare` | 0 | +6.45% | 0.573 | -2.43% | 4.67% | 965 | -0.2492 | 0/10 | `bare_plus_sell_trend_rising`, `bare_plus_sell_price_above_ma50` … |
| `full` | 7 | +0.82% | 0.228 | -1.71% | 0.86% | 410 | -0.7249 | 1/10 | `full_minus_sell_trend_rising`, `full_minus_sell_price_above_ma50` … |
| `full_minus_sell_trend_rising` | 6 | +0.82% | 0.228 | -1.71% | 0.86% | 410 | -0.7249 | 1/10 | `full`, `full_minus_sell_price_above_ma50` … |
| `full_minus_buy_trend_falling` | 6 | +0.80% | 0.208 | -1.66% | 0.87% | 414 | -0.7277 | 1/10 |  |
| `full_minus_sell_price_above_ma50` | 6 | +0.82% | 0.228 | -1.71% | 0.86% | 410 | -0.7249 | 1/10 | `full`, `full_minus_sell_trend_rising` … |
| `full_minus_buy_overbought` | 6 | +1.05% | 0.179 | -1.82% | 2.01% | 590 | -0.6682 | 0/10 |  |
| `full_minus_sell_oversold` | 6 | +0.82% | 0.228 | -1.71% | 0.86% | 410 | -0.7249 | 1/10 | `full`, `full_minus_sell_trend_rising` … |
| `full_minus_buy_macd_bearish` | 6 | +3.36% | 0.375 | -2.26% | 3.32% | 882 | -0.4038 | 1/10 |  |
| `full_minus_sell_macd_bullish` | 6 | +0.82% | 0.228 | -1.71% | 0.86% | 410 | -0.7249 | 1/10 | `full`, `full_minus_sell_trend_rising` … |
| `bare_plus_sell_trend_rising` | 1 | +6.45% | 0.573 | -2.43% | 4.67% | 965 | -0.2492 | 0/10 | `bare`, `bare_plus_sell_price_above_ma50` … |
| `bare_plus_buy_trend_falling` | 1 | +6.37% | 0.564 | -2.43% | 4.66% | 962 | -0.2580 | 0/10 |  |
| `bare_plus_sell_price_above_ma50` | 1 | +6.45% | 0.573 | -2.43% | 4.67% | 965 | -0.2492 | 0/10 | `bare`, `bare_plus_sell_trend_rising` … |
| `bare_plus_buy_overbought` | 1 | +3.43% | 0.378 | -2.26% | 3.32% | 884 | -0.3971 | 1/10 |  |
| `bare_plus_sell_oversold` | 1 | +6.45% | 0.573 | -2.43% | 4.67% | 965 | -0.2492 | 0/10 | `bare`, `bare_plus_sell_trend_rising` … |
| `bare_plus_buy_macd_bearish` | 1 | +0.97% | 0.168 | -1.82% | 2.02% | 598 | -0.6651 | 0/10 |  |
| `bare_plus_sell_macd_bullish` | 1 | +6.45% | 0.573 | -2.43% | 4.67% | 965 | -0.2492 | 0/10 | `bare`, `bare_plus_sell_trend_rising` … |

### Sharpe ratio per symbol, tuning window (the distinct trading rules)

| Symbol | `buy_and_hold` | `bare` | `full` | `full_minus_buy_trend_falling` | `full_minus_buy_overbought` | `full_minus_buy_macd_bearish` | `bare_plus_buy_trend_falling` | `bare_plus_buy_overbought` | `bare_plus_buy_macd_bearish` |
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

### What each override does, tuning window

Blocks = share of that side's crossover days on which the override's condition holds (pooled over symbols). Sharpe changes are medians over the ten symbols; up/down counts the symbols.

| Override | Side | Blocks | Removing it from full: median ΔSharpe | up / down | Adding it to bare: median ΔSharpe | up / down |
|---|---|---|---|---|---|---|
| `sell_trend_rising` | SELL | 0.9% | +0.0000 | 0 / 0 | +0.0000 | 0 / 0 |
| `buy_trend_falling` | BUY | 0.5% | +0.0000 | 4 / 3 | -0.0061 | 0 / 7 |
| `sell_price_above_ma50` | SELL | 2.0% | +0.0000 | 0 / 0 | +0.0000 | 0 / 0 |
| `buy_overbought` | BUY | 25.2% | +0.1070 | 7 / 3 | -0.0920 | 3 / 7 |
| `sell_oversold` | SELL | 13.1% | +0.0000 | 0 / 0 | +0.0000 | 0 / 0 |
| `buy_macd_bearish` | BUY | 53.6% | +0.1731 | 8 / 2 | -0.1993 | 1 / 9 |
| `sell_macd_bullish` | SELL | 60.6% | +0.0000 | 0 / 0 | +0.0000 | 0 / 0 |

### Ranking by the selection rule

| Rank | Variant | Score | Overrides |
|---|---|---|---|
| 1 | `bare` | -0.2492 | 0 |
| 2 | `bare_plus_sell_trend_rising` | -0.2492 | 1 |
| 3 | `bare_plus_sell_price_above_ma50` | -0.2492 | 1 |
| 4 | `bare_plus_sell_oversold` | -0.2492 | 1 |
| 5 | `bare_plus_sell_macd_bullish` | -0.2492 | 1 |
| 6 | `bare_plus_buy_trend_falling` | -0.2580 | 1 |
| 7 | `bare_plus_buy_overbought` | -0.3971 | 1 |
| 8 | `full_minus_buy_macd_bearish` | -0.4038 | 6 |
| 9 | `bare_plus_buy_macd_bearish` | -0.6651 | 1 |
| 10 | `full_minus_buy_overbought` | -0.6682 | 6 |
| 11 | `full_minus_sell_trend_rising` | -0.7249 | 6 |
| 12 | `full_minus_sell_price_above_ma50` | -0.7249 | 6 |
| 13 | `full_minus_sell_oversold` | -0.7249 | 6 |
| 14 | `full_minus_sell_macd_bullish` | -0.7249 | 6 |
| 15 | `full` | -0.7249 | 7 |
| 16 | `full_minus_buy_trend_falling` | -0.7277 | 6 |
