"""Plain-English explanations of a /signal result.

services/signal.py decides the signal; this module only describes it. It
evaluates no rule of its own: it is given the signal and reason code the
signal code chose, plus the numbers and thresholds that choice was made with
(SignalFacts), and puts them into a few sentences. So the text cannot
disagree with the signal, and each threshold lives in one place only.

The text is deterministic: the same inputs always give the same words.
"""

import math
from dataclasses import dataclass
from datetime import date

from services.decisions import CONFIDENCE_MAX, MAX_POSITION_PCT


@dataclass(frozen=True)
class SignalFacts:
    """What a signal was computed from. services.signal builds it.

    The indicator values are None when there was too little history to
    compute them, or when a fallback HOLD had no usable row at all.
    """

    # Daily bars of price history the signal was given.
    bars: int
    # The thresholds the signal code applies.
    min_bars: int
    trend_falling_slope: float
    overbought_rsi: float
    full_confidence_strength: float
    # Date of the bar the indicators were read from, when the prices are dated.
    as_of: date | None = None
    # (MA20 - MA50) / MA50: positive when the 20-day average is above.
    gap: float | None = None
    # services.signal.crossover_strength: the gap in units of daily volatility.
    strength: float | None = None
    rolling_volatility: float | None = None
    trend_slope: float | None = None
    rsi: float | None = None
    macd_histogram: float | None = None


def _percent(fraction: float, digits: int = 1) -> str:
    return f"{fraction * 100:.{digits}f}%"


def _heading(signal: str, facts: SignalFacts) -> str:
    if facts.as_of is None:
        return f"{signal}."
    return f"{signal} as of {facts.as_of.isoformat()}."


def _crossover(facts: SignalFacts) -> str | None:
    """Where the 20-day average sits against the 50-day, and how decisively."""
    if facts.gap is None or facts.strength is None or facts.rolling_volatility is None:
        return None

    side = "above" if facts.gap > 0 else "below"
    text = f"The 20-day average is {_percent(abs(facts.gap))} {side} the 50-day"

    if facts.rolling_volatility > 0 and math.isfinite(facts.strength):
        return (
            f"{text}, {facts.strength:.1f} times the typical daily move of "
            f"{_percent(facts.rolling_volatility)}"
        )
    return f"{text}, with no day-to-day price movement to measure the gap against"


def _trend(facts: SignalFacts) -> str:
    if facts.trend_slope is None:
        return "the 50-day trend is not available yet"
    return f"the 50-day average moved {facts.trend_slope * 100:+.1f}% over 5 days"


def _rsi(facts: SignalFacts) -> str:
    if facts.rsi is None:
        return "RSI is not available yet"
    return f"RSI is {facts.rsi:.1f} (limit {facts.overbought_rsi:g})"


def _macd(facts: SignalFacts) -> str:
    if facts.macd_histogram is None:
        return "the MACD histogram is not available yet"
    return f"the MACD histogram is {facts.macd_histogram:+.2f}"


def _veto(reason: str, facts: SignalFacts) -> str | None:
    """Why a bullish crossover was held back, naming the one veto that did it."""
    if reason == "buy_vetoed_trend_falling" and facts.trend_slope is not None:
        return (
            f"the 50-day average fell {_percent(abs(facts.trend_slope))} over 5 days, "
            f"more than the {_percent(abs(facts.trend_falling_slope), 0)} limit"
        )
    if reason == "buy_vetoed_overbought" and facts.rsi is not None:
        return f"RSI is {facts.rsi:.1f}, above the overbought limit of {facts.overbought_rsi:g}"
    if reason == "buy_vetoed_macd_bearish" and facts.macd_histogram is not None:
        return (
            f"the MACD histogram is {facts.macd_histogram:+.2f}, below zero, so momentum "
            "disagrees with the crossover"
        )
    return None


def _not_enough_history(facts: SignalFacts) -> str:
    one = facts.bars == 1
    return (
        f"There {'is' if one else 'are'} only {facts.bars} daily "
        f"{'bar' if one else 'bars'} of price history, and the signal needs at least "
        f"{facts.min_bars}. No position."
    )


NO_INDICATORS = (
    "No day has every indicator the signal needs yet: the 50-day average and its "
    "5-day slope need a longer run of complete prices. No position."
)
UNRELIABLE_INDICATORS = (
    "The indicators could not be computed reliably from this price data, so no "
    "crossover was read. No position."
)


def explain_signal(
    signal: str,
    reason: str,
    confidence: float,
    position_pct: float,
    facts: SignalFacts,
) -> str:
    """A few sentences on how `signal` was reached, for the /signal response.

    `reason` is the code services.signal reported; `position_pct` is the
    decision block's position. Only the veto named by `reason` is described:
    the checks run in order and the first that matches decides.
    """
    heading = _heading(signal, facts)
    crossover = _crossover(facts)

    if reason == "insufficient_price_history":
        return f"{heading} {_not_enough_history(facts)}"
    if reason == "insufficient_feature_data":
        return f"{heading} {NO_INDICATORS}"
    if reason == "no_ma_crossover":
        return (
            f"{heading} The 20-day and 50-day averages are equal, so there is no "
            "crossover. No position."
        )

    if crossover is not None:
        if reason == "ma_crossover_bullish":
            return (
                f"{heading} {crossover}: a bullish crossover, confidence {confidence:.2f} "
                f"({facts.full_confidence_strength:g} times or more earns the "
                f"{CONFIDENCE_MAX:g} cap). The trend, RSI and MACD checks all passed: "
                f"{_trend(facts)}, {_rsi(facts)}, and {_macd(facts)}. Suggested position: "
                f"{_percent(position_pct)} of the portfolio, at most "
                f"{_percent(MAX_POSITION_PCT, 0)}."
            )
        if reason == "ma_crossover_bearish":
            return (
                f"{heading} {crossover}: a bearish crossover, confidence {confidence:.2f}. "
                "The strategy is long-only, so SELL means holding no position (cash)."
            )
        because = _veto(reason, facts)
        if because is not None:
            return (
                f"{heading} {crossover}: a bullish crossover, but the BUY was held back "
                f"because {because}. No position."
            )

    if reason in ("missing_feature_columns", "invalid_feature_values", "invalid_confidence"):
        return f"{heading} {UNRELIABLE_INDICATORS}"

    # A reason code this module does not know yet still gets a truthful line
    # rather than an error; tests/test_explanations.py covers every known code.
    position = "No position." if position_pct == 0 else f"Position: {_percent(position_pct)}."
    return f"{heading} Reason code: {reason}. {position}"
