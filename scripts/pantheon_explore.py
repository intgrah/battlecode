"""Closer look at Pantheon spawn timing."""

from __future__ import annotations

import csv
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


def per_replay(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["replay"], []).append(r)
    return out


def show_spawn_pattern(rows: list[dict]) -> None:
    spawns = [r for r in rows if r["spawned"]]
    print(f"=== {rows[0]['replay']} ===  total spawns: {len(spawns)}")
    print(
        f"{'turn':>5} {'gap':>4} {'ti':>5} {'cost':>4} {'live':>4} {'harv':>4} {'inc':>6} {'units≠harv':>10}"
    )
    for i, s in enumerate(spawns):
        gap = s["turn"] - spawns[i - 1]["turn"] if i > 0 else s["turn"]
        units_no_harv = s["live_units"] - s["live_harvesters"]
        print(
            f"{s['turn']:5d} {gap:4d} {s['ti']:5d} {s['builder_cost']:4d} "
            f"{s['live_units']:4d} {s['live_harvesters']:4d} {s['income_recent']:6.2f} {units_no_harv:10d}"
        )


def show_pre_spawn_window(rows: list[dict], spawn_turn: int, window: int = 5) -> None:
    """Show the few turns before each post-initial spawn — what was the
    bottleneck right before spawning?
    """
    for i, r in enumerate(rows):
        if r["turn"] == spawn_turn:
            start = max(0, i - window)
            print(f"\n  Pre-spawn window for turn {spawn_turn}:")
            for j in range(start, i + 1):
                rr = rows[j]
                marker = " <- SPAWN" if rr["spawned"] else ""
                print(
                    f"    turn={rr['turn']:4d} ti={rr['ti']:5d} cost={rr['builder_cost']:4d}"
                    f" cd={rr['cd']} live={rr['live_units']:3d} harv={rr['live_harvesters']:2d}"
                    f" inc={rr['income_recent']:6.2f}{marker}"
                )


def main() -> None:
    rows = load()
    by_replay = per_replay(rows)
    for rs in by_replay.values():
        show_spawn_pattern(rs)
        # Show a sample late-game spawn for context.
        spawns = [r for r in rs if r["spawned"]]
        if len(spawns) >= 8:
            target = spawns[7]["turn"]
            show_pre_spawn_window(rs, target, window=8)
        print()


if __name__ == "__main__":
    main()
