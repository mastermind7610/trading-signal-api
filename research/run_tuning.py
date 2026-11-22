"""Run every variant on the tuning window and apply the selection rule.

    python -I research/run_tuning.py

Reads only bars up to research.config.TUNING_LAST_DAY. The selection rule is
the one pre-registered in research/RESEARCH.md: the strategy variant with
the highest median, over the ten symbols, of (variant Sharpe minus
buy-and-hold Sharpe); ties to four decimals go to fewer overrides, then to
table order. Writes, under research/results/:

- tuning_per_symbol.csv: every variant on every symbol.
- tuning_summary.csv: each variant's medians across symbols, its score, and
  which variants hold exactly the same positions.
- tuning_overrides.csv: what removing or adding each override does to the
  Sharpe ratio, and how often each one fires.
- tuning_tables.md: the tables for RESEARCH.md.
- selection.json: the chosen variant.
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research.config import (  # noqa: E402
    MANIFEST_PATH,
    RESULTS_DIR,
    SYMBOLS,
    TRADING_COST_PCT,
    TUNING_LAST_DAY,
)
from research.engine import (  # noqa: E402
    OVERRIDES,
    TUNING,
    all_variants,
    signal_inputs,
    simulate,
    variant_targets,
    window_prices,
)

METRICS = ["total_return", "sharpe", "max_drawdown", "exposure", "trades"]
BENCHMARK = "buy_and_hold"
SELECTION_RULE = (
    "Highest median over the ten symbols of (variant Sharpe minus buy-and-hold "
    "Sharpe) on the tuning window; ties to four decimals go to fewer overrides, "
    "then to table order. Exactly one variant goes to the holdout."
)


def _run() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, tuple[bytes, ...]]]:
    rows, fires = [], []
    positions: dict[str, list[bytes]] = {}

    for symbol in SYMBOLS:
        prices, first = window_prices(symbol, TUNING)
        inputs = signal_inputs(prices)
        scored = slice(first, len(prices) - 1)

        for variant in all_variants():
            targets = variant_targets(inputs, variant)
            result = simulate(prices, targets, first)
            rows.append(
                {
                    "variant": variant.name,
                    "symbol": symbol,
                    **{metric: result[metric] for metric in METRICS},
                    "first_return_day": result["first_return_day"],
                    "last_return_day": result["last_return_day"],
                    "days": result["days"],
                }
            )
            positions.setdefault(variant.name, []).append(targets[scored].tobytes())

        crossover = inputs.crossover[scored]
        for code, side in OVERRIDES.items():
            side_days = crossover == side
            blocked = side_days & inputs.conditions[code][scored]
            fires.append(
                {
                    "override": code,
                    "symbol": symbol,
                    "side_days": int(side_days.sum()),
                    "blocked_days": int(blocked.sum()),
                }
            )

    return (
        pd.DataFrame(rows),
        pd.DataFrame(fires),
        {name: tuple(parts) for name, parts in positions.items()},
    )


def _same_positions(positions: dict[str, tuple[bytes, ...]]) -> dict[str, list[str]]:
    """For each variant, the other variants with identical positions everywhere."""
    names = [variant.name for variant in all_variants()]
    return {
        name: [other for other in names if other != name and positions[other] == positions[name]]
        for name in names
    }


def _summary(per_symbol: pd.DataFrame, same: dict[str, list[str]]) -> pd.DataFrame:
    sharpe = per_symbol.pivot(index="symbol", columns="variant", values="sharpe")
    rows = []
    for order, variant in enumerate(all_variants()):
        group = per_symbol[per_symbol["variant"] == variant.name]
        difference = sharpe[variant.name] - sharpe[BENCHMARK]
        rows.append(
            {
                "variant": variant.name,
                "order": order,
                "overrides": len(variant.overrides),
                **{f"median_{metric}": float(group[metric].median()) for metric in METRICS},
                "score": round(float(difference.median()), 4),
                "beats_buy_and_hold": int((difference > 0).sum()),
                "same_positions_as": " ".join(same[variant.name]),
            }
        )
    return pd.DataFrame(rows)


def _override_effects(per_symbol: pd.DataFrame, fires: pd.DataFrame) -> pd.DataFrame:
    sharpe = per_symbol.pivot(index="symbol", columns="variant", values="sharpe")
    rows = []
    for code, side in OVERRIDES.items():
        removed = sharpe[f"full_minus_{code}"] - sharpe["full"]
        added = sharpe[f"bare_plus_{code}"] - sharpe["bare"]
        fired = fires[fires["override"] == code]
        rows.append(
            {
                "override": code,
                "side": side,
                "blocks_share_of_side_days": fired["blocked_days"].sum() / fired["side_days"].sum(),
                "removing_median_sharpe_change": round(float(removed.median()), 4),
                "removing_raises_sharpe_on": int((removed > 0).sum()),
                "removing_lowers_sharpe_on": int((removed < 0).sum()),
                "adding_median_sharpe_change": round(float(added.median()), 4),
                "adding_raises_sharpe_on": int((added > 0).sum()),
                "adding_lowers_sharpe_on": int((added < 0).sum()),
            }
        )
    return pd.DataFrame(rows)


def _select(summary: pd.DataFrame) -> pd.Series:
    candidates = summary[summary["variant"] != BENCHMARK]
    ranked = candidates.sort_values(
        ["score", "overrides", "order"], ascending=[False, True, True], kind="stable"
    )
    return ranked


def _markdown(summary, per_symbol, effects, ranked, distinct) -> str:
    lines = [
        "### Every variant, tuning window (medians over the ten symbols)",
        "",
        "Score = median of (variant Sharpe minus buy-and-hold Sharpe). "
        "Beats B&H = symbols on which the variant's Sharpe is higher.",
        "",
        "| Variant | Overrides | Return | Sharpe | Max drawdown | Exposure | Trades "
        "| Score | Beats B&H | Same positions as |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in summary.itertuples():
        same = row.same_positions_as.split()
        same_text = ", ".join(f"`{name}`" for name in same[:2]) + (" …" if len(same) > 2 else "")
        lines.append(
            f"| `{row.variant}` | {row.overrides} | {row.median_total_return:+.2%} "
            f"| {row.median_sharpe:.3f} | {row.median_max_drawdown:.2%} "
            f"| {row.median_exposure:.2%} | {row.median_trades:.0f} "
            f"| {row.score:+.4f} | {row.beats_buy_and_hold}/10 | {same_text} |"
        )

    sharpe = per_symbol.pivot(index="symbol", columns="variant", values="sharpe")[distinct]
    sharpe = sharpe.loc[list(SYMBOLS)]
    lines += [
        "",
        "### Sharpe ratio per symbol, tuning window (the distinct trading rules)",
        "",
        "| Symbol | " + " | ".join(f"`{name}`" for name in distinct) + " |",
        "|---|" + "---|" * len(distinct),
    ]
    for symbol, values in sharpe.iterrows():
        lines.append(f"| {symbol} | " + " | ".join(f"{value:.3f}" for value in values) + " |")

    lines += [
        "",
        "### What each override does, tuning window",
        "",
        "Blocks = share of that side's crossover days on which the override's "
        "condition holds (pooled over symbols). Sharpe changes are medians over "
        "the ten symbols; up/down counts the symbols.",
        "",
        "| Override | Side | Blocks | Removing it from full: median ΔSharpe | up / down "
        "| Adding it to bare: median ΔSharpe | up / down |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in effects.itertuples():
        lines.append(
            f"| `{row.override}` | {row.side} | {row.blocks_share_of_side_days:.1%} "
            f"| {row.removing_median_sharpe_change:+.4f} "
            f"| {row.removing_raises_sharpe_on} / {row.removing_lowers_sharpe_on} "
            f"| {row.adding_median_sharpe_change:+.4f} "
            f"| {row.adding_raises_sharpe_on} / {row.adding_lowers_sharpe_on} |"
        )

    lines += ["", "### Ranking by the selection rule", "", "| Rank | Variant | Score | Overrides |"]
    lines.append("|---|---|---|---|")
    for rank, row in enumerate(ranked.itertuples(), start=1):
        lines.append(f"| {rank} | `{row.variant}` | {row.score:+.4f} | {row.overrides} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    # The tables use non-ASCII characters; a Windows console defaults to cp1252.
    sys.stdout.reconfigure(encoding="utf-8")
    per_symbol, fires, positions = _run()
    same = _same_positions(positions)
    summary = _summary(per_symbol, same)
    effects = _override_effects(per_symbol, fires)
    ranked = _select(summary)
    chosen = ranked.iloc[0]

    # One representative per distinct set of positions, in table order.
    distinct, seen = [], set()
    for variant in all_variants():
        if positions[variant.name] not in seen:
            seen.add(positions[variant.name])
            distinct.append(variant.name)
    strategy_rules = [name for name in distinct if name != BENCHMARK]

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    per_symbol.to_csv(RESULTS_DIR / "tuning_per_symbol.csv", index=False, lineterminator="\n")
    summary.drop(columns="order").to_csv(
        RESULTS_DIR / "tuning_summary.csv", index=False, lineterminator="\n"
    )
    effects.to_csv(RESULTS_DIR / "tuning_overrides.csv", index=False, lineterminator="\n")
    (RESULTS_DIR / "tuning_tables.md").write_text(
        _markdown(summary, per_symbol, effects, ranked, distinct), encoding="utf-8", newline="\n"
    )

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    selection = {
        "chosen": chosen["variant"],
        "overrides": sorted(
            next(v for v in all_variants() if v.name == chosen["variant"]).overrides
        ),
        "score": float(chosen["score"]),
        "beats_buy_and_hold": int(chosen["beats_buy_and_hold"]),
        "same_positions_as": chosen["same_positions_as"].split(),
        "in_sample_edge": bool(chosen["score"] > 0),
        "rule": SELECTION_RULE,
        "made_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "tuning_last_day": TUNING_LAST_DAY.isoformat(),
        "trading_cost_pct": TRADING_COST_PCT,
        "strategy_variants_tried": len(all_variants()) - 1,
        "distinct_strategy_rules": len(strategy_rules),
        "distinct_rule_representatives": strategy_rules,
        "data_sha256": {symbol: entry["sha256"] for symbol, entry in manifest["files"].items()},
        "ranking": [
            {"variant": row.variant, "score": row.score, "overrides": row.overrides}
            for row in ranked.itertuples()
        ],
    }
    (RESULTS_DIR / "selection.json").write_text(
        json.dumps(selection, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    print((RESULTS_DIR / "tuning_tables.md").read_text(encoding="utf-8"))
    print(f"Strategy variants tried: {selection['strategy_variants_tried']}")
    print(f"Distinct strategy rules: {len(strategy_rules)}: {', '.join(strategy_rules)}")
    print(
        f"Chosen: {selection['chosen']} (score {selection['score']:+.4f}, beats buy-and-hold "
        f"on {selection['beats_buy_and_hold']}/10, same positions as "
        f"{selection['same_positions_as'] or 'no other variant'})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
