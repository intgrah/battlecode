"""Plot bench_nav results from CSV as one massive figure.

Scenarios side by side (columns), algorithms as rows.
4 metrics per scenario: time histogram, optimality histogram, reach %, first move %.

Usage:
    python scripts/bench_nav_plot.py [bench_nav.csv]
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

METRICS_PER_SCENARIO = 4


def _plot_row(
    axes_row: list,
    ad: pd.DataFrame,
    *,
    first_row: bool,
    scenario: str,
) -> None:
    times = ad["time_us"].dropna()
    reachable = ad[ad["reachable"] == 1]
    opts = pd.to_numeric(reachable["opt_ratio"], errors="coerce").dropna()
    reached = reachable["reached_goal"]
    fm = pd.to_numeric(reachable["first_move_correct"], errors="coerce").dropna()

    ax = axes_row[0]
    t_clipped = times.clip(upper=10000)
    if len(t_clipped) > 0:
        ax.hist(t_clipped, bins=50, color="steelblue", edgecolor="none")
    for p, color, ls in [
        (0.5, "red", "--"),
        (0.95, "orange", "--"),
        (1.0, "darkred", "-"),
    ]:
        v = times.quantile(p) if len(times) > 0 else 0
        plabel = f"p{int(p * 100)}"
        ax.axvline(
            v, color=color, linestyle=ls, linewidth=0.8, label=f"{plabel}={v:.0f}",
        )
    ax.legend(fontsize=5, loc="upper right")
    ax.tick_params(labelsize=5)
    if first_row:
        ax.set_title(f"{scenario} — Time (us)", fontsize=7)

    ax = axes_row[1]
    if len(opts) > 0:
        o_clipped = opts.clip(upper=5.0)
        ax.hist(o_clipped, bins=50, color="seagreen", edgecolor="none")
    ax.axvline(1.0, color="black", linestyle="-", linewidth=0.5)
    for p, color, ls in [
        (0.5, "red", "--"),
        (0.95, "orange", "--"),
        (1.0, "darkred", "-"),
    ]:
        v = opts.quantile(p) if len(opts) > 0 else 0
        plabel = f"p{int(p * 100)}"
        if v > 0:
            ax.axvline(
                min(v, 5.0),
                color=color,
                linestyle=ls,
                linewidth=0.8,
                label=f"{plabel}={v:.3f}",
            )
    ax.legend(fontsize=5, loc="upper right")
    ax.tick_params(labelsize=5)
    if first_row:
        ax.set_title(f"{scenario} — Optimality", fontsize=7)

    ax = axes_row[2]
    n_found = int(reached.sum()) if len(reached) > 0 else 0
    n_reachable = len(reachable)
    if n_reachable > 0:
        pct_found = 100 * n_found / n_reachable
        ax.barh([0], [pct_found], color="seagreen", height=0.6)
        ax.barh([0], [100 - pct_found], left=[pct_found], color="tomato", height=0.6)
        ax.text(
            50,
            0,
            f"{pct_found:.1f}%",
            ha="center",
            va="center",
            fontsize=6,
            fontweight="bold",
            color="white",
        )
    ax.set_xlim(0, 100)
    ax.set_yticks([])
    ax.tick_params(labelsize=5)
    if first_row:
        ax.set_title(f"{scenario} — Reach %", fontsize=7)

    ax = axes_row[3]
    if len(fm) > 0:
        acc_pct = 100 * fm.mean()
        ax.barh([0], [acc_pct], color="mediumpurple", height=0.6)
        ax.barh([0], [100 - acc_pct], left=[acc_pct], color="lightgray", height=0.6)
        ax.text(
            50,
            0,
            f"{acc_pct:.1f}%",
            ha="center",
            va="center",
            fontsize=6,
            fontweight="bold",
        )
    ax.set_xlim(0, 100)
    ax.set_yticks([])
    ax.tick_params(labelsize=5)
    if first_row:
        ax.set_title(f"{scenario} — 1st move %", fontsize=7)


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
    scenarios = sorted(df["scenario"].unique())
    algos = sorted(df["algo"].unique())
    n_scenarios = len(scenarios)
    n_algos = len(algos)
    n_cols = n_scenarios * METRICS_PER_SCENARIO

    fig, axes = plt.subplots(
        n_algos,
        n_cols,
        figsize=(7 * n_scenarios, 2.0 * n_algos),
        squeeze=False,
    )
    fig.suptitle("Navigation Benchmark", fontsize=16, fontweight="bold", y=1.0)

    for row, algo in enumerate(algos):
        axes[row][0].set_ylabel(algo, fontsize=5, rotation=0, ha="right", va="center")
        for si, scenario in enumerate(scenarios):
            col_offset = si * METRICS_PER_SCENARIO
            ad = df[(df["algo"] == algo) & (df["scenario"] == scenario)]
            row_axes = [axes[row][col_offset + j] for j in range(METRICS_PER_SCENARIO)]
            _plot_row(row_axes, ad, first_row=row == 0, scenario=scenario)

    plt.tight_layout()
    out = Path(__file__).resolve().parent / "bench_nav.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
