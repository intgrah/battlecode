import random
import time
from bench_nav.common import INF, MAPS_DIR, SCENARIOS, SEED
from bench_nav.map_data import (
    build_cost,
    build_nb,
    build_pnb,
    load_map,
    place_roads,
)
from bench_nav.map_data_jps import build_dir_of_offset, build_pnb_dir
from bench_nav.sssp.bfs_jps_list import bfs_jps_list

N = 100


def run() -> None:
    bad_samples: list[tuple[float, str, str, int]] = []  # (us, map, scenario, start)

    for mf in sorted(MAPS_DIR.glob("*.map26")):
        m = load_map(mf)
        tiles = [t for row in m.rows for t in row.tiles]
        w, h = m.width, m.height
        n = w * h
        nb = build_nb(w, h)
        for scenario in SCENARIOS:
            cost = build_cost(tiles, n)
            passable = [i for i in range(n) if cost[i] < INF]
            if scenario == "with_roads":
                place_roads(tiles, cost, nb, passable)
            build_pnb(nb, cost)
            pnb_dir = build_pnb_dir(w, h, cost)
            dir_off = build_dir_of_offset(w)
            passable = [i for i in range(n) if cost[i] < INF]
            rng = random.Random(SEED)
            sources = [rng.choice(passable) for _ in range(N)]

            for s in sources:
                t0 = time.perf_counter()
                bfs_jps_list(n, pnb_dir, dir_off, s)
                us = (time.perf_counter() - t0) * 1e6
                bad_samples.append((us, mf.stem, scenario, s))

    bad_samples.sort(reverse=True)
    print("top 20 slowest runs (bfs-jps-list):")
    for us, mp, sc, s in bad_samples[:20]:
        print(f"  {us:7.1f}us  {mp:30s} {sc:12s} start={s}")

    # re-run the top 20 to see reproducibility
    print("\nre-running top 20 (5 trials each):")
    for us0, mp, sc, s in bad_samples[:20]:
        m = load_map(MAPS_DIR / f"{mp}.map26")
        tiles = [t for row in m.rows for t in row.tiles]
        w, h = m.width, m.height
        n = w * h
        nb = build_nb(w, h)
        cost = build_cost(tiles, n)
        if sc == "with_roads":
            passable = [i for i in range(n) if cost[i] < INF]
            place_roads(tiles, cost, nb, passable)
        pnb_dir = build_pnb_dir(w, h, cost)
        dir_off = build_dir_of_offset(w)

        runs = []
        for _ in range(5):
            t0 = time.perf_counter()
            bfs_jps_list(n, pnb_dir, dir_off, s)
            runs.append((time.perf_counter() - t0) * 1e6)
        print(
            f"  orig={us0:7.1f}us  "
            f"reruns={[f'{r:.1f}' for r in runs]}  {mp} {sc} start={s}"
        )


if __name__ == "__main__":
    run()
