"""Fit a model to Pantheon's spawn decisions.

Reads pantheon_spawn.csv produced by pantheon_spawn.py.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

CSV = Path("pantheon_spawn.csv")


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
                "spawned": r["spawned"] == "True",
            }
            rows.append(row)
    return rows


def summarize_initial(rows: list[dict]) -> None:
    print("=== INITIAL SPAWNS PER REPLAY ===")
    by_replay: dict[str, list[dict]] = {}
    for r in rows:
        by_replay.setdefault(r["replay"], []).append(r)
    for replay, rs in by_replay.items():
        spawns = [r for r in rs if r["spawned"]]
        first6 = spawns[:6]
        print(f"\n{replay}:")
        for r in first6:
            print(
                f"  turn={r['turn']:4d}  ti={r['ti']:4d}  "
                f"cost={r['builder_cost']:3d}  cd={r['cd']}  "
                f"live={r['live_units']:2d}  harv={r['live_harvesters']}"
            )


def candidate_set(rows: list[dict], skip_initial: int = 4) -> list[dict]:
    """Decision points: turns where the core had cd=0 (could act),
    excluding the first `skip_initial` spawns (which appear unconditional).
    """
    out = []
    spawn_count = 0
    for r in rows:
        if r["spawned"]:
            spawn_count += 1
        if r["cd"] != 0:
            continue
        if r["spawned_count"] < skip_initial:
            continue
        if r["ti"] < r["builder_cost"]:
            continue
        out.append(r)
    return out


def find_split(rows: list[dict], feature: str) -> tuple[float, float, int, int]:
    """Best single-threshold split: feature >= t -> spawn=1.
    Returns (threshold, accuracy, tp, fp). Naive but reveals the rule.
    """
    pos = [r for r in rows if r["spawned"]]
    neg = [r for r in rows if not r["spawned"]]
    n = len(rows)
    if not pos or not neg:
        return (0.0, 0.0, 0, 0)
    vals = sorted({r[feature] for r in rows})
    best = (vals[0], 0.0, 0, 0)
    for t in vals:
        tp = sum(1 for r in pos if r[feature] >= t)
        fp = sum(1 for r in neg if r[feature] >= t)
        tn = len(neg) - fp
        acc = (tp + tn) / n
        if acc > best[1]:
            best = (t, acc, tp, fp)
    return best


def fit_decision_tree(rows: list[dict]) -> None:
    """Greedy single-feature splits — clearer than a black-box model."""
    print(
        "\n=== SINGLE-FEATURE THRESHOLDS (after first 4 unconditional, cd=0, can-afford) ==="
    )
    candidates = candidate_set(rows, skip_initial=4)
    pos = sum(1 for r in candidates if r["spawned"])
    neg = len(candidates) - pos
    print(f"Decision points: {len(candidates)} ({pos} spawn / {neg} no-spawn)")
    print(f"  Baseline (always-no): {neg / len(candidates):.3f}")
    print()
    feats = [
        "ti",
        "builder_cost",
        "scale_milli",
        "live_units",
        "live_harvesters",
        "rounds_since_spawn",
        "income_recent",
        "turn",
        "spawned_count",
    ]
    for f in feats:
        t, acc, tp, fp = find_split(candidates, f)
        print(f"  {f:22s} >= {t:8.2f}: acc={acc:.3f}  tp={tp}  fp={fp}")


def fit_ratio(rows: list[dict]) -> None:
    """Try ti / builder_cost as the spawn signal."""
    print("\n=== RATIO ti / builder_cost (after first 4 unconditional, cd=0) ===")
    candidates = candidate_set(rows, skip_initial=4)
    pos = [r for r in candidates if r["spawned"]]
    neg = [r for r in candidates if not r["spawned"]]
    print(
        f"  spawn rows: ti/cost min={min(r['ti'] / r['builder_cost'] for r in pos):.2f}  "
        f"max={max(r['ti'] / r['builder_cost'] for r in pos):.2f}  "
        f"median={sorted(r['ti'] / r['builder_cost'] for r in pos)[len(pos) // 2]:.2f}"
    )
    print(
        f"  no-spawn rows: ti/cost min={min(r['ti'] / r['builder_cost'] for r in neg):.2f}  "
        f"max={max(r['ti'] / r['builder_cost'] for r in neg):.2f}  "
        f"median={sorted(r['ti'] / r['builder_cost'] for r in neg)[len(neg) // 2]:.2f}"
    )

    # Search ratio threshold.
    n = len(candidates)
    best = (0.0, 0.0, 0, 0)
    ratios = sorted({r["ti"] / r["builder_cost"] for r in candidates})
    for t in ratios:
        tp = sum(1 for r in pos if r["ti"] / r["builder_cost"] >= t)
        fp = sum(1 for r in neg if r["ti"] / r["builder_cost"] >= t)
        tn = len(neg) - fp
        acc = (tp + tn) / n
        if acc > best[1]:
            best = (t, acc, tp, fp)
    print(
        f"\n  best: ti/cost >= {best[0]:.3f}  acc={best[1]:.3f}  tp={best[2]}/{len(pos)}  fp={best[3]}/{len(neg)}"
    )


def fit_compound(rows: list[dict]) -> None:
    """Try compound rules: 'ti - builder_cost >= K' (post-spend buffer)."""
    print("\n=== POST-SPEND BUFFER  (ti - builder_cost >= K)  ===")
    candidates = candidate_set(rows, skip_initial=4)
    pos = [r for r in candidates if r["spawned"]]
    neg = [r for r in candidates if not r["spawned"]]

    n = len(candidates)
    best = (0, 0.0, 0, 0)
    diffs = sorted({r["ti"] - r["builder_cost"] for r in candidates})
    for t in diffs:
        tp = sum(1 for r in pos if r["ti"] - r["builder_cost"] >= t)
        fp = sum(1 for r in neg if r["ti"] - r["builder_cost"] >= t)
        tn = len(neg) - fp
        acc = (tp + tn) / n
        if acc > best[1]:
            best = (t, acc, tp, fp)
    print(
        f"  best: ti - cost >= {best[0]}  acc={best[1]:.3f}  tp={best[2]}/{len(pos)}  fp={best[3]}/{len(neg)}"
    )


def income_at_spawn(rows: list[dict]) -> None:
    print("\n=== UNIT-CAP CHECK ===")
    spawns = [r for r in rows if r["spawned"]]
    print(f"  max live_units at spawn time: {max(r['live_units'] for r in spawns)}")
    by_replay: dict[str, int] = {}
    for r in rows:
        if r["spawned"]:
            by_replay[r["replay"]] = max(by_replay.get(r["replay"], 0), r["live_units"])
    for replay, m in by_replay.items():
        print(f"  {replay}: max live={m}")


def main() -> None:
    if not CSV.exists():
        print(f"Run pantheon_spawn.py first to create {CSV}")
        sys.exit(1)
    rows = load()
    print(f"Loaded {len(rows)} turns; spawns={sum(1 for r in rows if r['spawned'])}")
    summarize_initial(rows)
    fit_decision_tree(rows)
    fit_ratio(rows)
    fit_compound(rows)
    income_at_spawn(rows)


if __name__ == "__main__":
    main()
