"""Plot bench_nav results from CSV.

Per scenario: horizontal box plots for time and optimality, horizontal bar charts
for reach% and first-move%. Algorithms on the y-axis, shared across all columns.

Usage:
    python scripts/bench_nav_plot.py [bench_nav.csv]
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ALGO_CLASS_COLORS: dict[str, str] = {
    "astar heap cheb w=1": "#4682b4",
    "astar heap cheb w=3": "#1e3a5f",
    "astar bucket cheb w=1": "#e07020",
    "astar bucket cheb w=3": "#8b4513",
    "astar heap apsp": "#2ca02c",
    "bfs": "#d62728",
    "bfs roadopt": "#b22222",
    "bibfs": "#ff6961",
    "gbfs": "#9467bd",
    "dijkstra heap": "#8c564b",
    "dijkstra bucket": "#e377c2",
    "hpastar": "#7f7f7f",
}


def _algo_class(name: str) -> str:
    for prefix in ALGO_CLASS_COLORS:
        if name.startswith(prefix):
            return prefix
    return name


def _algo_color(name: str) -> str:
    return ALGO_CLASS_COLORS.get(_algo_class(name), "#333333")


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
    scenarios: list[str] = sorted(df["scenario"].unique())
    algos: list[str] = list(dict.fromkeys(df["algo"]))
    n_scenarios = len(scenarios)
    n_algos = len(algos)
    cols_per_scenario = 4

    width_ratios = [4, 2, 1, 1] * n_scenarios
    fig, axes = plt.subplots(
        1,
        n_scenarios * cols_per_scenario,
        figsize=(8 * n_scenarios, 0.35 * n_algos + 1),
        squeeze=False,
        gridspec_kw={"width_ratios": width_ratios, "wspace": 0.15},
    )
    fig.suptitle("Navigation Benchmark", fontsize=14, fontweight="bold")

    for si, scenario in enumerate(scenarios):
        sd = df[df["scenario"] == scenario]
        col_base = si * cols_per_scenario

        time_data: list[list[float]] = []
        opt_data: list[list[float]] = []
        reach_pcts: list[float] = []
        fm_pcts: list[float] = []

        for algo in algos:
            ad = sd[sd["algo"] == algo]
            times = ad["time_us"].dropna().tolist()
            time_data.append(times or [0])

            reachable = ad[ad["reachable"] == 1]
            opts = (
                pd.to_numeric(reachable["opt_ratio"], errors="coerce").dropna().tolist()
            )
            opt_data.append(opts or [1.0])

            reached = reachable["reached_goal"]
            n_reachable = len(reachable)
            n_found = int(reached.sum()) if n_reachable > 0 else 0
            reach_pcts.append(100 * n_found / n_reachable if n_reachable > 0 else 0)

            fm = pd.to_numeric(
                reachable["first_move_correct"],
                errors="coerce",
            ).dropna()
            fm_pcts.append(100 * fm.mean() if len(fm) > 0 else 0)

        positions = list(range(n_algos))

        ax = axes[0][col_base]
        bp = ax.boxplot(
            time_data,
            vert=False,
            positions=positions,
            widths=0.6,
            patch_artist=True,
            whis=(0, 100),
            medianprops={"color": "darkred", "linewidth": 1.2},
        )
        colors = [_algo_color(a) for a in algos]
        for patch, c in zip(bp["boxes"], colors, strict=True):
            patch.set_facecolor(c)
            patch.set_alpha(0.7)
        ax.axvline(2000, color="red", linestyle="--", linewidth=0.8, alpha=0.7)
        ax.set_yticks(positions)
        if si == 0:
            ax.set_yticklabels(algos, fontsize=6)
        else:
            ax.set_yticklabels([])
        ax.set_title(f"{scenario} — Time (us)", fontsize=8)
        ax.tick_params(labelsize=6)
        ax.invert_yaxis()

        ax = axes[0][col_base + 1]
        bp = ax.boxplot(
            opt_data,
            vert=False,
            positions=positions,
            widths=0.6,
            patch_artist=True,
            whis=(0, 100),
            medianprops={"color": "darkred", "linewidth": 1.2},
        )
        for patch, c in zip(bp["boxes"], colors, strict=True):
            patch.set_facecolor(c)
            patch.set_alpha(0.7)
        ax.axvline(1.0, color="black", linestyle="-", linewidth=0.5)
        ax.set_yticks(positions)
        ax.set_yticklabels([], fontsize=6)
        ax.set_title(f"{scenario} — Optimality", fontsize=8)
        ax.tick_params(labelsize=6)
        ax.invert_yaxis()

        ax = axes[0][col_base + 2]
        ax.barh(positions, reach_pcts, color="seagreen", height=0.6, alpha=0.8)
        for i, v in enumerate(reach_pcts):
            ax.text(
                max(v - 2, 1),
                i,
                f"{v:.0f}",
                va="center",
                ha="right",
                fontsize=5,
                color="white",
                fontweight="bold",
            )
        ax.set_xlim(0, 105)
        ax.set_yticks(positions)
        ax.set_yticklabels([], fontsize=6)
        ax.set_title(f"{scenario} — Reach %", fontsize=8)
        ax.tick_params(labelsize=6)
        ax.invert_yaxis()

        ax = axes[0][col_base + 3]
        ax.barh(positions, fm_pcts, color="mediumpurple", height=0.6, alpha=0.8)
        for i, v in enumerate(fm_pcts):
            ax.text(
                max(v - 2, 1),
                i,
                f"{v:.0f}",
                va="center",
                ha="right",
                fontsize=5,
                color="white",
                fontweight="bold",
            )
        ax.set_xlim(0, 105)
        ax.set_yticks(positions)
        ax.set_yticklabels([], fontsize=6)
        ax.set_title(f"{scenario} — 1st move %", fontsize=8)
        ax.tick_params(labelsize=6)
        ax.invert_yaxis()

    fig.subplots_adjust(left=0.12, right=0.98, top=0.93, bottom=0.05)
    out = Path(__file__).resolve().parent / "bench_nav.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
