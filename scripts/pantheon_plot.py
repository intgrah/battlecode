"""Plot Pantheon's spawn behaviour."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

CSV = Path("pantheon_spawn.csv")
OUT = Path("pantheon_plots")


def load() -> list[dict]:
    rows = []
    with CSV.open() as f:
        for r in csv.DictReader(f):
            row = {
                "replay": r["replay"],
                "turn": int(r["turn"]),
                "ti": int(r["ti"]),
                "scale_milli": int(r["scale_milli"]),
                "builder_cost": int(r["builder_cost"]),
                "cd": int(r["cd"]),
                "rounds_since_spawn": int(r["rounds_since_spawn"]),
                "spawned_count": int(r["spawned_count"]),
                "live_units": int(r["live_units"]),
                "live_harvesters": int(r["live_harvesters"]),
                "income_recent": float(r["income_recent"]),
                "delivery_rate_16": float(r["delivery_rate_16"]),
                "delivery_rate_100": float(r["delivery_rate_100"]),
                "ti_collected": int(r["ti_collected"]),
                "spawned": r["spawned"] == "True",
            }
            row["units_no_harv"] = row["live_units"] - row["live_harvesters"]
            row["ti_minus_cost"] = row["ti"] - row["builder_cost"]
            row["ti_div_cost"] = (
                row["ti"] / row["builder_cost"] if row["builder_cost"] else 0
            )
            rows.append(row)
    return rows


def per_replay(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["replay"], []).append(r)
    return out


def plot_timelines(rows: list[dict]) -> None:
    by_replay = per_replay(rows)
    n = len(by_replay)
    fig, axes = plt.subplots(n, 1, figsize=(13, 2.5 * n), sharex=False)
    if n == 1:
        axes = [axes]
    for ax, (replay, rs) in zip(axes, by_replay.items()):
        turns = np.array([r["turn"] for r in rs])
        ti = np.array([r["ti"] for r in rs])
        cost = np.array([r["builder_cost"] for r in rs])
        spawn_turns = np.array([r["turn"] for r in rs if r["spawned"]])

        ax.plot(turns, ti, color="C0", linewidth=0.8, label="Ti")
        ax.plot(turns, cost, color="C1", linewidth=0.8, label="builder cost")
        ax.plot(
            turns, 4 * cost, color="C1", linestyle=":", linewidth=0.8, label="4 × cost"
        )
        for t in spawn_turns:
            ax.axvline(t, color="green", alpha=0.4, linewidth=0.6)
        ax.scatter(
            spawn_turns,
            [10] * len(spawn_turns),
            color="green",
            marker="^",
            s=15,
            zorder=5,
            label=f"spawn (n={len(spawn_turns)})",
        )
        ax.set_title(f"{replay}", fontsize=10)
        ax.set_ylabel("Ti")
        ax.legend(loc="upper right", fontsize=7)
        ax.grid(alpha=0.3)
    axes[-1].set_xlabel("Round")
    plt.tight_layout()
    out = OUT / "timelines.png"
    plt.savefig(out, dpi=120)
    print(f"  -> {out}")
    plt.close()


def plot_decision_scatter(rows: list[dict]) -> None:
    """ti vs cost colored by spawn/no-spawn, free-decision turns only."""
    cand = [
        r
        for r in rows
        if r["cd"] == 0
        and r["ti"] >= r["builder_cost"]
        and r["spawned_count"] >= 4
        and r["units_no_harv"] < 50
    ]
    pos = [r for r in cand if r["spawned"]]
    neg = [r for r in cand if not r["spawned"]]

    fig, ax = plt.subplots(figsize=(9, 7))
    ax.scatter(
        [r["builder_cost"] for r in neg],
        [r["ti"] for r in neg],
        s=4,
        alpha=0.15,
        color="grey",
        label=f"no spawn (n={len(neg)})",
    )
    ax.scatter(
        [r["builder_cost"] for r in pos],
        [r["ti"] for r in pos],
        s=22,
        color="green",
        edgecolor="darkgreen",
        linewidth=0.5,
        label=f"spawn (n={len(pos)})",
        zorder=5,
    )
    xs = np.linspace(50, 380, 100)
    ax.plot(
        xs, xs, color="black", linestyle="--", linewidth=0.7, label="ti = cost (afford)"
    )
    ax.plot(
        xs, 3 * xs, color="orange", linestyle="--", linewidth=0.7, label="ti = 3 × cost"
    )
    ax.plot(
        xs, 4 * xs, color="red", linestyle="--", linewidth=0.7, label="ti = 4 × cost"
    )
    ax.plot(
        xs, 5 * xs, color="purple", linestyle="--", linewidth=0.7, label="ti = 5 × cost"
    )
    ax.set_xlabel("Scaled builder cost (Ti)")
    ax.set_ylabel("Current Ti")
    ax.set_title("Spawn vs no-spawn at free-decision turns")
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    out = OUT / "decision_scatter.png"
    plt.savefig(out, dpi=120)
    print(f"  -> {out}")
    plt.close()


def plot_ratio_histogram(rows: list[dict]) -> None:
    cand = [
        r
        for r in rows
        if r["cd"] == 0
        and r["ti"] >= r["builder_cost"]
        and r["spawned_count"] >= 4
        and r["units_no_harv"] < 50
    ]
    pos_ratio = [r["ti_div_cost"] for r in cand if r["spawned"]]
    neg_ratio = [r["ti_div_cost"] for r in cand if not r["spawned"]]

    fig, ax = plt.subplots(figsize=(9, 5))
    bins = np.linspace(1, 7, 31)
    ax.hist(
        neg_ratio,
        bins=bins,
        alpha=0.45,
        color="grey",
        density=True,
        label=f"no spawn (n={len(neg_ratio)})",
    )
    ax.hist(
        pos_ratio,
        bins=bins,
        alpha=0.65,
        color="green",
        density=True,
        label=f"spawn (n={len(pos_ratio)})",
    )
    ax.axvline(
        np.median(pos_ratio),
        color="green",
        linestyle="--",
        label=f"spawn median={np.median(pos_ratio):.2f}",
    )
    ax.axvline(
        np.median(neg_ratio),
        color="grey",
        linestyle="--",
        label=f"no-spawn median={np.median(neg_ratio):.2f}",
    )
    ax.set_xlabel("ti / builder_cost")
    ax.set_ylabel("density")
    ax.set_title("Ti / cost ratio at decision time")
    ax.legend()
    ax.grid(alpha=0.3)
    plt.tight_layout()
    out = OUT / "ratio_histogram.png"
    plt.savefig(out, dpi=120)
    print(f"  -> {out}")
    plt.close()


def plot_gap_vs_ratio(rows: list[dict]) -> None:
    """rounds_since_spawn (x) vs ti_div_cost (y), colored by outcome."""
    cand = [
        r
        for r in rows
        if r["cd"] == 0
        and r["ti"] >= r["builder_cost"]
        and r["spawned_count"] >= 4
        and r["units_no_harv"] < 50
    ]
    pos = [r for r in cand if r["spawned"]]
    neg = [r for r in cand if not r["spawned"]]

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(
        [r["rounds_since_spawn"] for r in neg],
        [r["ti_div_cost"] for r in neg],
        s=4,
        alpha=0.15,
        color="grey",
        label=f"no spawn (n={len(neg)})",
    )
    ax.scatter(
        [r["rounds_since_spawn"] for r in pos],
        [r["ti_div_cost"] for r in pos],
        s=22,
        color="green",
        edgecolor="darkgreen",
        linewidth=0.5,
        label=f"spawn (n={len(pos)})",
        zorder=5,
    )
    ax.axhline(
        3.73,
        color="red",
        linestyle="--",
        linewidth=0.7,
        label="depth-2 tree split ti/cost = 3.73",
    )
    ax.axvline(
        6,
        color="orange",
        linestyle="--",
        linewidth=0.7,
        label="grid-search rounds_since = 6",
    )
    ax.set_xlabel("rounds_since_spawn (log scale)")
    ax.set_ylabel("ti / cost")
    ax.set_xscale("symlog", linthresh=1)
    ax.set_xlim(0, 1000)
    ax.set_ylim(1, 7)
    ax.legend()
    ax.grid(alpha=0.3)
    ax.set_title("Spawn vs no-spawn in (gap, ti/cost) space")
    plt.tight_layout()
    out = OUT / "gap_vs_ratio.png"
    plt.savefig(out, dpi=120)
    print(f"  -> {out}")
    plt.close()


def plot_units_curve(rows: list[dict]) -> None:
    by_replay = per_replay(rows)
    fig, ax = plt.subplots(figsize=(11, 5))
    for replay, rs in by_replay.items():
        turns = [r["turn"] for r in rs]
        units = [r["units_no_harv"] for r in rs]
        ax.plot(turns, units, label=replay.split("vs_")[-1], linewidth=0.9)
    ax.axhline(50, color="red", linestyle="--", linewidth=0.7, label="cap=50")
    ax.set_xlabel("Round")
    ax.set_ylabel("Live units (excluding harvesters)")
    ax.set_title("Pantheon's army-size curve per game")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    out = OUT / "units_curve.png"
    plt.savefig(out, dpi=120)
    print(f"  -> {out}")
    plt.close()


def main() -> None:
    OUT.mkdir(exist_ok=True)
    rows = load()
    print("Plotting...")
    plot_timelines(rows)
    plot_decision_scatter(rows)
    plot_ratio_histogram(rows)
    plot_gap_vs_ratio(rows)
    plot_units_curve(rows)
    print("Done.")


if __name__ == "__main__":
    main()
