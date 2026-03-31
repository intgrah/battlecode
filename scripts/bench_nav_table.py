"""Print bench_nav results as a terminal table, one section per scenario.

Usage:
    python scripts/bench_nav_table.py [bench_nav.csv]
"""

import sys
from pathlib import Path

import pandas as pd


def _print_scenario(df: pd.DataFrame, scenario: str) -> None:
    algos = list(dict.fromkeys(df["algo"]))

    hdr = (
        f"{'Algorithm':<50}"
        f" {'t_p50':>7} {'t_p100':>7}"
        f" {'o_p50':>7} {'o_p100':>7}"
        f" {'reach%':>7} {'1st_mv%':>7}"
    )
    print(f"\n  {scenario.upper()}")
    print(hdr)
    print("-" * len(hdr))

    for algo in algos:
        ad = df[df["algo"] == algo]
        times = ad["time_us"]
        reachable = ad[ad["reachable"] == 1]
        opts = pd.to_numeric(reachable["opt_ratio"], errors="coerce").dropna()
        n_reached = int(reachable["reached_goal"].sum()) if len(reachable) > 0 else 0
        n_reachable = len(reachable)
        fm = pd.to_numeric(reachable["first_move_correct"], errors="coerce").dropna()

        t50 = times.quantile(0.5) if len(times) > 0 else 0
        t100 = times.max() if len(times) > 0 else 0
        o50 = opts.quantile(0.5) if len(opts) > 0 else 0
        o100 = opts.max() if len(opts) > 0 else 0
        reach_pct = 100 * n_reached / n_reachable if n_reachable > 0 else 0
        fm_pct = 100 * fm.mean() if len(fm) > 0 else 0

        print(
            f"{algo:<50}"
            f" {t50:>7.0f} {t100:>7.0f}"
            f" {o50:>7.3f} {o100:>7.3f}"
            f" {reach_pct:>6.1f}% {fm_pct:>6.1f}%",
        )


def main() -> None:
    path = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(__file__).resolve().parent / "bench_nav.csv"
    )
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        print("Run bench_nav.py first.", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(path)
    for scenario in sorted(df["scenario"].unique()):
        _print_scenario(df[df["scenario"] == scenario], scenario)


if __name__ == "__main__":
    main()
