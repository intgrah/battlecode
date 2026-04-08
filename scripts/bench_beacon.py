"""Benchmark + correctness check: noparent2 vs beacon."""
from __future__ import annotations

import gc
import random
import sys
import time

from scripts.bench_nav import (
    SCENARIOS,
    SEED,
    MapData,
    sssp_dijkstra_bucket_noparent2,
    sssp_dijkstra_bucket_noparent_beacon,
)

MAPS_DIR = MapData.__module__ and __import__("pathlib").Path(__file__).resolve().parent.parent / "maps"

N_SOURCES = 1000


def main() -> None:
    map_files = sorted(MAPS_DIR.glob("*.map26"))
    if not map_files:
        print(f"No .map26 files in {MAPS_DIR}", file=sys.stderr)
        sys.exit(1)

    times_np2: dict[str, list[float]] = {}
    times_beacon: dict[str, list[float]] = {}
    failures = 0

    for mf in map_files:
        md = MapData(mf)
        if not md.passable:
            continue

        rng = random.Random(SEED)
        sources = [rng.choice(md.passable) for _ in range(N_SOURCES)]

        for scenario in SCENARIOS:
            md.reset_cost_no_roads()
            if scenario == "with_roads":
                md.place_roads()

            label = f"{md.name}/{scenario}"
            sys.stderr.write(f"\r{label:40s}")
            sys.stderr.flush()

            for si in sources:
                gc.disable()

                t0 = time.perf_counter()
                result_np2 = sssp_dijkstra_bucket_noparent2(md, si)
                us_np2 = (time.perf_counter() - t0) * 1e6
                times_np2.setdefault(scenario, []).append(us_np2)

                t0 = time.perf_counter()
                result_beacon = sssp_dijkstra_bucket_noparent_beacon(md, si)
                us_beacon = (time.perf_counter() - t0) * 1e6
                times_beacon.setdefault(scenario, []).append(us_beacon)

                gc.enable()

                if result_np2 != result_beacon:
                    failures += 1
                    if failures <= 10:
                        diffs = [
                            i for i in range(len(result_np2)) if result_np2[i] != result_beacon[i]
                        ]
                        print(
                            f"\nFAIL: {md.name}/{scenario} src={si} "
                            f"({len(diffs)} tiles differ, first: idx={diffs[0]} "
                            f"np2={result_np2[diffs[0]]} beacon={result_beacon[diffs[0]]})",
                            file=sys.stderr,
                        )

    sys.stderr.write("\r" + " " * 60 + "\r")

    if failures:
        print(f"CORRECTNESS: {failures} failures")
    else:
        print("CORRECTNESS: all passed")

    print()
    for scenario in SCENARIOS:
        print(f"  {scenario.upper()}")
        print(f"  {'Algorithm':<24s} {'p50':>8s} {'p90':>8s} {'p99':>8s} {'p100':>8s}")
        print(f"  {'-' * 56}")
        for name, ts_dict in [("noparent2", times_np2), ("beacon", times_beacon)]:
            ts = sorted(ts_dict.get(scenario, []))
            if not ts:
                continue
            nt = len(ts)
            p50 = ts[nt // 2]
            p90 = ts[int(nt * 0.9)]
            p99 = ts[int(nt * 0.99)]
            p100 = ts[-1]
            print(f"  {name:<24s} {p50:>7.0f}us {p90:>7.0f}us {p99:>7.0f}us {p100:>7.0f}us")
        print()


if __name__ == "__main__":
    main()
