"""Run the chosen variant once on the holdout window.

    python -I research/run_holdout.py

Runs exactly two things on the last five years (return days after
research.config.TUNING_LAST_DAY): the variant named in
research/results/selection.json, and buy-and-hold as its benchmark.

It refuses to run:
- if anything under research/ is uncommitted, so the choice is on record
  before the holdout is read;
- if research/results/holdout.json already exists, so the holdout is
  touched once;
- if the selection was made on different data than the cached CSVs.

The result files are written before anything is printed. The pre-registered
test is applied as written: an edge only if the chosen variant's Sharpe beats
buy-and-hold's on at least 8 of the 10 symbols and the median difference is
positive.
"""

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research.config import (  # noqa: E402
    MANIFEST_PATH,
    RESEARCH_DIR,
    RESULTS_DIR,
    SYMBOLS,
    TRADING_COST_PCT,
)
from research.engine import (  # noqa: E402
    HOLDOUT,
    signal_inputs,
    simulate,
    variant_by_name,
    variant_targets,
    window_prices,
)

METRICS = ["total_return", "sharpe", "max_drawdown", "exposure", "trades"]
BENCHMARK = "buy_and_hold"
SELECTION_PATH = RESULTS_DIR / "selection.json"
HOLDOUT_PATH = RESULTS_DIR / "holdout.json"
EDGE_MIN_WINS = 8


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=RESEARCH_DIR, capture_output=True, text=True, check=True
    ).stdout.strip()


def _refusal() -> str | None:
    if HOLDOUT_PATH.exists():
        return f"{HOLDOUT_PATH.name} exists: the holdout has already been run once."
    if not SELECTION_PATH.exists():
        return "No selection.json: run research/run_tuning.py and commit its choice first."
    if _git("status", "--porcelain", "--", str(RESEARCH_DIR)):
        return "research/ has uncommitted changes: commit the choice before the holdout."

    selection = json.loads(SELECTION_PATH.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    cached = {symbol: entry["sha256"] for symbol, entry in manifest["files"].items()}
    if selection["data_sha256"] != cached:
        return "selection.json was made on different data than the cached CSVs."
    return None


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")

    refusal = _refusal()
    if refusal:
        print(f"Refusing to run the holdout: {refusal}")
        return 1

    selection = json.loads(SELECTION_PATH.read_text(encoding="utf-8"))
    chosen = variant_by_name(selection["chosen"])
    benchmark = variant_by_name(BENCHMARK)
    commit = _git("rev-parse", "HEAD")

    rows = []
    for symbol in SYMBOLS:
        prices, first = window_prices(symbol, HOLDOUT)
        inputs = signal_inputs(prices)
        row = {"symbol": symbol}
        for label, variant in (("chosen", chosen), ("buy_and_hold", benchmark)):
            result = simulate(prices, variant_targets(inputs, variant), first, TRADING_COST_PCT)
            row.update({f"{label}_{metric}": result[metric] for metric in METRICS})
            row["first_return_day"] = result["first_return_day"]
            row["last_return_day"] = result["last_return_day"]
            row["days"] = result["days"]
        row["sharpe_difference"] = round(row["chosen_sharpe"] - row["buy_and_hold_sharpe"], 4)
        rows.append(row)

    per_symbol = pd.DataFrame(rows)
    wins = int((per_symbol["sharpe_difference"] > 0).sum())
    median_difference = round(float(per_symbol["sharpe_difference"].median()), 4)
    edge = wins >= EDGE_MIN_WINS and median_difference > 0

    medians = {
        f"median_{label}_{metric}": float(per_symbol[f"{label}_{metric}"].median())
        for label in ("chosen", "buy_and_hold")
        for metric in METRICS
    }
    summary = {
        "variant": chosen.name,
        "ran_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "code_commit": commit,
        "first_return_day": per_symbol["first_return_day"].min(),
        "last_return_day": per_symbol["last_return_day"].max(),
        "days": sorted(per_symbol["days"].unique().tolist()),
        "trading_cost_pct": TRADING_COST_PCT,
        "beats_buy_and_hold_on": wins,
        "median_sharpe_difference": median_difference,
        "edge_rule": (
            f"edge only if Sharpe beats buy-and-hold on >= {EDGE_MIN_WINS} of 10 "
            "symbols and the median difference is positive"
        ),
        "edge": edge,
        **medians,
    }

    # Write before printing anything, so the one run is on record whatever happens.
    per_symbol.to_csv(RESULTS_DIR / "holdout_per_symbol.csv", index=False, lineterminator="\n")
    HOLDOUT_PATH.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")

    print(f"Holdout: {summary['first_return_day']} to {summary['last_return_day']}, "
          f"{summary['days']} return days; variant {chosen.name}; code {commit[:7]}")
    print()
    print("| Symbol | B&H return | B&H Sharpe | B&H max DD | Chosen return | Chosen Sharpe "
          "| Chosen max DD | Chosen exposure | Chosen trades | ΔSharpe |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for row in per_symbol.itertuples():
        print(
            f"| {row.symbol} | {row.buy_and_hold_total_return:+.2%} "
            f"| {row.buy_and_hold_sharpe:.3f} "
            f"| {row.buy_and_hold_max_drawdown:.2%} | {row.chosen_total_return:+.2%} "
            f"| {row.chosen_sharpe:.3f} | {row.chosen_max_drawdown:.2%} "
            f"| {row.chosen_exposure:.2%} | {row.chosen_trades} | {row.sharpe_difference:+.3f} |"
        )
    print(
        f"| Median | {medians['median_buy_and_hold_total_return']:+.2%} "
        f"| {medians['median_buy_and_hold_sharpe']:.3f} "
        f"| {medians['median_buy_and_hold_max_drawdown']:.2%} "
        f"| {medians['median_chosen_total_return']:+.2%} "
        f"| {medians['median_chosen_sharpe']:.3f} "
        f"| {medians['median_chosen_max_drawdown']:.2%} "
        f"| {medians['median_chosen_exposure']:.2%} | {medians['median_chosen_trades']:.0f} "
        f"| {median_difference:+.3f} |"
    )
    print()
    print(f"Beats buy-and-hold on {wins}/10; median ΔSharpe {median_difference:+.4f}; "
          f"edge by the pre-registered test: {'YES' if edge else 'NO'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
