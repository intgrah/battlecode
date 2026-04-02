"""Benchmark nahhh's A* on real maps.

Reports p50 and p100 times across all maps, 200 random pairs each.

Usage:
    python scripts/bench_nahhh_astar.py
"""

from __future__ import annotations

import random
import statistics
import sys
import time
from pathlib import Path

from proto.cambc_pb2 import Map as PbMap

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "nahhh_archive" / "bots" / "nahhh"))
from astar import astar_walk

MAPS_DIR = Path(__file__).resolve().parent.parent / "maps"
N_PAIRS = 200
SEED = 42


def load_map(path: Path) -> tuple[int, int, set[tuple[int, int]]]:
    m = PbMap()
    m.ParseFromString(path.read_bytes())
    walls: set[tuple[int, int]] = set()
    for y, row in enumerate(m.rows):
        for x, tile in enumerate(row.tiles):
            if tile in (1, 2, 3):
                walls.add((x, y))
    return m.width, m.height, walls


def bench_map(map_path: Path) -> list[float]:
    w, h, walls = load_map(map_path)
    known = {(x, y) for x in range(w) for y in range(h)}
    passable = [(x, y) for x in range(w) for y in range(h) if (x, y) not in walls]
    if len(passable) < 2:
        return []

    rng = random.Random(SEED)
    times_us: list[float] = []

    for _ in range(N_PAIRS):
        (sx, sy), (gx, gy) = rng.sample(passable, 2)

        t0 = time.perf_counter()
        astar_walk(
            sx, sy, gx, gy,
            walls, set(), known, set(), set(),
            w, h,
        )
        t1 = time.perf_counter()
        times_us.append((t1 - t0) * 1e6)

    return times_us


def main() -> None:
    map_files = sorted(MAPS_DIR.glob("*.map26"))
    print(f"nahhh astar_walk: {len(map_files)} maps, {N_PAIRS} pairs each\n")

    all_times: list[float] = []
    for mf in map_files:
        times = bench_map(mf)
        if not times:
            continue
        times.sort()
        p50 = times[len(times) // 2]
        p100 = times[-1]
        print(f"  {mf.stem:30s}  p50={p50:6.0f}us  p100={p100:7.0f}us")
        all_times.extend(times)

    if all_times:
        all_times.sort()
        p50 = all_times[len(all_times) // 2]
        p100 = all_times[-1]
        mean = statistics.mean(all_times)
        print(f"\n  {'OVERALL':30s}  p50={p50:6.0f}us  p100={p100:7.0f}us  mean={mean:.0f}us")


if __name__ == "__main__":
    main()
