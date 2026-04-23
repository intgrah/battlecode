from __future__ import annotations

import contextlib
import csv
import random
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt

from bench_nav import spsp, sssp
from bench_nav.common import CE, INF, MAPS_DIR, SCENARIOS, SEED, Path_, bfs_dist
from bench_nav.map_data import (
    build_cost,
    build_nb,
    build_pnb,
    build_pnb_dual,
    build_pnb_navbfs,
    build_pnb_navdijkstra,
    build_pnbc,
    build_pnbc_navdijkstra,
    load_map,
    place_roads,
)
from bench_nav.map_data_jps import (
    build_dir_of_offset,
    build_pnb_by_offset,
    build_pnb_dir,
)
from bench_nav.reference import (
    dijkstra_full,
    optimal_first_moves,
    path_cost,
    reference_dist,
    validate_path,
)
from bench_nav.spsp.astar_dial_landmark import (
    astar_dial_landmark,
    astar_dial_landmark_cheb,
)

if TYPE_CHECKING:
    import argparse

type SpspFn = Callable[[int, int], Path_]
type SsspFn = Callable[[int], list[int]]


def progress_bar(current: int, total: int, width: int = 40, prefix: str = "") -> None:
    frac = current / total if total else 1.0
    filled = int(width * frac)
    bar = "#" * filled + "-" * (width - filled)
    pct = frac * 100
    sys.stderr.write(f"\r{prefix}[{bar}] {pct:5.1f}% ({current}/{total})")
    sys.stderr.flush()
    if current >= total:
        sys.stderr.write("\n")


CSV_FIELDS = [
    "algo",
    "scenario",
    "map",
    "start",
    "goal",
    "time_us",
    "reachable",
    "reached_goal",
    "opt_ratio",
    "first_move_correct",
]


def _build_spsp_algos(
    w: int,
    h: int,
    n: int,
    cost: list[int],
    pnb: list[list[int]],
    pnb1: list[list[int]],
    pnb3: list[list[int]],
    pnb_push: list[list[int]],
    pnb_set: list[list[int]],
    sources: set[int],
    goals: set[int],
    selected: set[str],
) -> list[tuple[str, SpspFn]]:
    algos: list[tuple[str, SpspFn]] = []

    def add(name: str, fn: SpspFn) -> None:
        if name in selected:
            algos.append((name, fn))

    add(
        "astar-heap-cheb",
        lambda start, goal: spsp.astar_heap_cheb(w, n, cost, pnb, start, goal),
    )
    add(
        "astar-dial-cheb",
        lambda start, goal: spsp.astar_dial_cheb(w, n, cost, pnb, start, goal),
    )
    # Padded cost for JPS: size (w+1)*(h+1) with border = INF. Lets scan
    # bodies drop all bounds checks (off-edge wraps to border via negative
    # indexing or positive overflow).
    if "astar-jps" in selected or "astar-jps-dial" in selected:
        stride_pad = w + 1
        n_pad = stride_pad * (h + 1)
        cost_pad = [INF] * n_pad
        for y in range(h):
            for x in range(w):
                cost_pad[y * stride_pad + x] = cost[y * w + x]

        def _pad(i: int) -> int:
            return (i // w) * stride_pad + (i % w)

        add(
            "astar-jps",
            lambda start, goal: spsp.astar_jps(
                stride_pad, n_pad, cost_pad, _pad(start), _pad(goal), w
            ),
        )
        add(
            "astar-jps-dial",
            lambda start, goal: spsp.astar_jps_dial(
                stride_pad, n_pad, cost_pad, _pad(start), _pad(goal), w
            ),
        )

    if "astar-heap-apsp" in selected or "astar-dial-apsp" in selected:
        apsp = spsp.precompute_apsp(n, cost, pnb)
        add(
            "astar-heap-apsp",
            lambda start, goal: spsp.astar_heap_apsp(n, cost, pnb, apsp, start, goal),
        )
        add(
            "astar-dial-apsp",
            lambda start, goal: spsp.astar_dial_apsp(n, cost, pnb, apsp, start, goal),
        )

    add("bfs", lambda start, goal: spsp.bfs(n, pnb, start, goal))
    add("bfs-01", lambda start, goal: spsp.bfs_01(n, cost, pnb, start, goal))
    add("bfs-dist", lambda start, goal: spsp.bfs_dist(n, pnb, start, goal))
    add("bfs-expand", lambda start, goal: spsp.bfs_expand(n, cost, pnb, start, goal))
    add("bfs-roadopt", lambda start, goal: spsp.bfs_roadopt(n, cost, pnb, start, goal))
    add(
        "navbfs",
        lambda start, goal: spsp.navbfs(n, cost, pnb, pnb_push, pnb_set, start, goal),
    )
    add(
        "navbfs-noextract",
        lambda start, goal: spsp.navbfs_noextract(n, pnb_push, pnb_set, start, goal),
    )
    add("bibfs", lambda start, goal: spsp.bibfs(n, pnb, start, goal))
    add("gbfs", lambda start, goal: spsp.gbfs(w, n, pnb, start, goal))
    add(
        "dijkstra-heap",
        lambda start, goal: spsp.dijkstra_heap(n, cost, pnb, start, goal),
    )
    add(
        "dijkstra-dial",
        lambda start, goal: spsp.dijkstra_dial(n, cost, pnb, start, goal),
    )
    add(
        "dijkstra-dial-dual",
        lambda start, goal: spsp.dijkstra_dial_dual(
            n, cost, pnb, pnb1, pnb3, start, goal
        ),
    )

    if "hpastar" in selected:
        hpa_graph = spsp.precompute_hpa(w, h, cost)
        add("hpastar", lambda start, goal: spsp.hpastar(w, hpa_graph, start, goal))

    if "astar-dial-precomp-cheb" in selected:
        cheb_cache: dict[int, list[int]] = {}
        for si in sources:
            sx, sy = si % w, si // w
            cheb_cache[si] = [max(abs(i % w - sx), abs(i // w - sy)) for i in range(n)]
        add(
            "astar-dial-precomp-cheb",
            lambda start, goal: spsp.astar_dial_precomp(
                n, cost, pnb, cheb_cache[start], start, goal
            ),
        )

    if "astar-dial-precomp-bfs" in selected:
        bfs_h_cache: dict[int, list[int]] = {}
        for si in sources:
            bfs_h_cache[si] = bfs_dist(n, pnb, si)
        add(
            "astar-dial-precomp-bfs",
            lambda start, goal: spsp.astar_dial_precomp(
                n, cost, pnb, bfs_h_cache[start], start, goal
            ),
        )

    if "astar-heap-precomp-bfs" in selected:
        bfs_goal_cache: dict[int, list[int]] = {}
        for gi in goals:
            bfs_goal_cache[gi] = bfs_dist(n, pnb, gi)
        add(
            "astar-heap-precomp-bfs",
            lambda start, goal: spsp.astar_heap_bfs(
                n, cost, pnb, bfs_goal_cache[goal], start, goal
            ),
        )

    landmark_ks = [
        k
        for k in (2, 4, 8)
        if f"landmark-{k}" in selected or f"landmark-{k}-cheb" in selected
    ]
    if landmark_ks:
        passable = [i for i in range(n) if cost[i] < INF]
        max_k = max(landmark_ks)
        landmarks: list[int] = []
        landmark_dists: list[list[int]] = []
        # Farthest-point selection
        if passable:
            landmarks.append(passable[0])
            landmark_dists.append(bfs_dist(n, pnb, passable[0]))
            for _ in range(max_k - 1):
                best = -1
                best_min_d = -1
                for tile in passable:
                    min_d = min(landmark_dists[j][tile] for j in range(len(landmarks)))
                    if min_d > best_min_d:
                        best_min_d = min_d
                        best = tile
                landmarks.append(best)
                landmark_dists.append(bfs_dist(n, pnb, best))

        for k in landmark_ks:
            ld = landmark_dists[:k]
            if f"landmark-{k}" in selected:
                add(
                    f"landmark-{k}",
                    lambda start, goal, _ld=ld: astar_dial_landmark(
                        n, cost, pnb, _ld, start, goal
                    ),
                )
            if f"landmark-{k}-cheb" in selected:
                add(
                    f"landmark-{k}-cheb",
                    lambda start, goal, _ld=ld: astar_dial_landmark_cheb(
                        w, n, cost, pnb, _ld, start, goal
                    ),
                )

    add(
        "biastar-dial-cheb",
        lambda start, goal: spsp.biastar_dial_cheb(w, n, cost, pnb, start, goal),
    )
    add(
        "biastar-dial-cheb-ft",
        lambda start, goal: spsp.biastar_dial_cheb_ft(w, n, cost, pnb, start, goal),
    )
    add(
        "astar-cheb+bw-dijkstra",
        lambda start, goal: spsp.astar_dial_cheb_bw_dijkstra(
            w, n, cost, pnb, start, goal
        ),
    )

    return algos


def _build_sssp_algos(
    n: int,
    cost: list[int],
    pnb: list[list[int]],
    pnbc: list[list[tuple[int, int]]],
    pnb1: list[list[int]],
    pnb3: list[list[int]],
    pnb_push: list[list[int]],
    pnb_set: list[list[int]],
    pnb_push_dij: list[list[int]],
    pnb_set_dij: list[list[int]],
    pnb_push_dij_c: list[list[tuple[int, int]]],
    pnb_set_dij_c: list[list[tuple[int, int]]],
    pnb_dir: list[list[list[int]]],
    pnb_by_offset: list[list[list[int]]],
    dir_of_offset: list[int],
    w: int,
    selected: set[str],
) -> list[tuple[str, SsspFn]]:
    algos: list[tuple[str, SsspFn]] = []

    def add(name: str, fn: SsspFn) -> None:
        if name in selected:
            algos.append((name, fn))

    add("bfs", lambda start: sssp.bfs(n, pnb, start))
    add("bfs-expand", lambda start: sssp.bfs_expand(n, cost, pnb, start))
    add("bfs-level", lambda start: sssp.bfs_level(n, pnb, start))
    add("bfs-buckets", lambda start: sssp.bfs_buckets(n, pnb, start))
    add("dijkstra-heap", lambda start: sssp.dijkstra_heap(n, cost, pnb, start))
    add("dijkstra-dial", lambda start: sssp.dijkstra_dial(n, cost, pnb, start))
    add(
        "dijkstra-dial-skip",
        lambda start: sssp.dijkstra_dial_skip(
            n, cost, pnb_push_dij, pnb_set_dij, start
        ),
    )
    add(
        "dijkstra-dial-skip-pnbc",
        lambda start: sssp.dijkstra_dial_skip_pnbc(
            n, pnb_push_dij_c, pnb_set_dij_c, start
        ),
    )
    add("dijkstra-dial-pnbc", lambda start: sssp.dijkstra_dial_pnbc(n, pnbc, start))
    add(
        "dijkstra-flat",
        lambda start: sssp.dijkstra_flat(n, cost, pnb, start),
    )
    add(
        "dijkstra-flat-prealloc",
        lambda start: sssp.dijkstra_flat_prealloc(n, cost, pnb, start),
    )
    add(
        "dijkstra-dial-dual",
        lambda start: sssp.dijkstra_dial_dual(n, pnb1, pnb3, start),
    )
    add(
        "dijkstra-dial-unrolled",
        lambda start: sssp.dijkstra_dial_unrolled(n, cost, pnb, start),
    )
    add("bfs-skip", lambda start: sssp.bfs_skip(n, pnb_push, pnb_set, start))
    add(
        "bfs-skip-level",
        lambda start: sssp.bfs_skip_level(n, pnb_push, pnb_set, start),
    )
    add(
        "bfs-jps",
        lambda start: sssp.bfs_jps(n, pnb_dir, dir_of_offset, start),
    )
    add(
        "bfs-jps-list",
        lambda start: sssp.bfs_jps_list(n, pnb_dir, dir_of_offset, start),
    )
    add(
        "bfs-jps-list-dbl",
        lambda start: sssp.bfs_jps_list_dbl(n, pnb_dir, dir_of_offset, start),
    )
    add(
        "bfs-jps-list-merge",
        lambda start: sssp.bfs_jps_list_merge(n, pnb_dir, dir_of_offset, start),
    )
    add(
        "bfs-jps-list-merge-off",
        lambda start: sssp.bfs_jps_list_merge_off(n, pnb_by_offset, start),
    )
    add(
        "bfs-jps-list-defer",
        lambda start: sssp.bfs_jps_list_defer(n, pnb_by_offset, start),
    )
    add(
        "bfs-jps-list-off",
        lambda start: sssp.bfs_jps_list_off(n, pnb_by_offset, start),
    )
    add("spfa-slf", lambda start: sssp.spfa_slf(n, cost, pnb, start))
    add("bellman-ford", lambda start: sssp.bellman_ford(n, cost, pnb, start))

    return algos


ALL_SPSP_NAMES: list[str] = [
    "astar-heap-cheb",
    "astar-dial-cheb",
    "astar-jps",
    "astar-jps-dial",
    "astar-heap-apsp",
    "astar-dial-apsp",
    "bfs",
    "bfs-01",
    "bfs-dist",
    "bfs-expand",
    "bfs-roadopt",
    "navbfs",
    "navbfs-noextract",
    "bibfs",
    "gbfs",
    "dijkstra-heap",
    "dijkstra-dial",
    "dijkstra-dial-dual",
    "hpastar",
    "astar-dial-precomp-cheb",
    "astar-dial-precomp-bfs",
    "astar-heap-precomp-bfs",
    "landmark-2",
    "landmark-4",
    "landmark-8",
    "landmark-2-cheb",
    "landmark-4-cheb",
    "landmark-8-cheb",
    "biastar-dial-cheb",
    "biastar-dial-cheb-ft",
    "astar-cheb+bw-dijkstra",
]

ALL_SSSP_NAMES: list[str] = [
    "bfs",
    "bfs-expand",
    "bfs-level",
    "bfs-buckets",
    "dijkstra-heap",
    "dijkstra-dial",
    "dijkstra-dial-skip",
    "dijkstra-dial-skip-pnbc",
    "dijkstra-dial-pnbc",
    "dijkstra-flat",
    "dijkstra-flat-prealloc",
    "dijkstra-dial-dual",
    "dijkstra-dial-unrolled",
    "bfs-skip",
    "bfs-skip-level",
    "bfs-jps",
    "bfs-jps-list",
    "bfs-jps-list-dbl",
    "bfs-jps-list-merge",
    "bfs-jps-list-merge-off",
    "bfs-jps-list-defer",
    "bfs-jps-list-off",
    "spfa-slf",
    "bellman-ford",
]


def bench_spsp(args: argparse.Namespace) -> None:
    if args.list:
        for name in ALL_SPSP_NAMES:
            print(name)
        sys.exit(0)

    selected: set[str] = set(ALL_SPSP_NAMES)
    if args.algos:
        selected = set(args.algos)
        unknown = selected - set(ALL_SPSP_NAMES)
        if unknown:
            print(f"Unknown algorithms: {', '.join(sorted(unknown))}", file=sys.stderr)
            print("Use --list to see names.", file=sys.stderr)
            sys.exit(1)

    n_pairs: int = args.samples

    map_files = sorted(MAPS_DIR.glob("*.map26"))
    if not map_files:
        print(f"No .map26 files in {MAPS_DIR}", file=sys.stderr)
        sys.exit(1)

    out_path = Path("bench_nav.csv")
    out_f = out_path.open("w", newline="")
    writer = csv.DictWriter(out_f, fieldnames=CSV_FIELDS)
    writer.writeheader()

    for mf in map_files:
        m = load_map(mf)
        name = mf.stem
        tiles: list[int] = [tile for row in m.rows for tile in row.tiles]
        w, h = m.width, m.height
        n = w * h
        nb = build_nb(w, h)

        cost = build_cost(tiles, n)
        passable = [i for i in range(n) if cost[i] < INF]
        if not passable:
            continue

        rng = random.Random(SEED)
        pairs = [(rng.choice(passable), rng.choice(passable)) for _ in range(n_pairs)]

        for scenario in SCENARIOS:
            cost = build_cost(tiles, n)
            if scenario == "with_roads":
                passable = [i for i in range(n) if cost[i] < INF]
                place_roads(tiles, cost, nb, passable)

            pnb = build_pnb(nb, cost)
            pnb1, pnb3 = build_pnb_dual(nb, cost)
            pnb_push, pnb_set = build_pnb_navbfs(w, h, cost)
            passable = [i for i in range(n) if cost[i] < INF]

            prefix = f"{name:24s} {scenario:11s} "

            gt_cache: dict[int, list[int]] = {}
            first_moves_cache: dict[tuple[int, int], set[int]] = {}
            for start, goal in pairs:
                if start not in gt_cache:
                    gt_cache[start] = dijkstra_full(n, cost, pnb, start)
                key = (start, goal)
                if key not in first_moves_cache:
                    first_moves_cache[key] = optimal_first_moves(
                        n, cost, pnb, start, goal, gt_cache[start]
                    )

            unique_sources = {start for start, _ in pairs}
            unique_goals = {goal for _, goal in pairs}
            algos = _build_spsp_algos(
                w,
                h,
                n,
                cost,
                pnb,
                pnb1,
                pnb3,
                pnb_push,
                pnb_set,
                unique_sources,
                unique_goals,
                selected,
            )

            for algo_name, algo_fn in algos:
                for start, goal in pairs:
                    gd = gt_cache[start][goal]
                    reachable = gd < INF

                    if not reachable:
                        t0 = time.perf_counter()
                        algo_fn(start, goal)
                        us = (time.perf_counter() - t0) * 1e6
                        row: dict[str, str | int] = {
                            "algo": algo_name,
                            "scenario": scenario,
                            "map": name,
                            "start": start,
                            "goal": goal,
                            "time_us": f"{us:.1f}",
                            "reachable": 0,
                            "reached_goal": "",
                            "opt_ratio": "",
                            "first_move_correct": "",
                        }
                        writer.writerow(row)
                        continue

                    if start == goal:
                        row = {
                            "algo": algo_name,
                            "scenario": scenario,
                            "map": name,
                            "start": start,
                            "goal": goal,
                            "time_us": "0.0",
                            "reachable": 1,
                            "reached_goal": 1,
                            "opt_ratio": "1.0",
                            "first_move_correct": 1,
                        }
                        writer.writerow(row)
                        continue

                    t0 = time.perf_counter()
                    path = algo_fn(start, goal)
                    us = (time.perf_counter() - t0) * 1e6

                    reached = 0
                    opt = ""
                    fm = 0
                    if path is not None and len(path) >= 1:
                        validate_path(w, n, cost, name, path, start, algo_name)
                        pc = path_cost(w, cost, path)
                        if path[-1] == goal and pc < INF:
                            reached = 1
                            opt = f"{pc / gd:.6f}"
                        fm_set = first_moves_cache[(start, goal)]
                        if len(path) >= 2 and path[1] in fm_set:
                            fm = 1

                    row = {
                        "algo": algo_name,
                        "scenario": scenario,
                        "map": name,
                        "start": start,
                        "goal": goal,
                        "time_us": f"{us:.1f}",
                        "reachable": 1,
                        "reached_goal": reached,
                        "opt_ratio": opt,
                        "first_move_correct": fm,
                    }
                    writer.writerow(row)

                sys.stderr.write(f"\r{prefix}{algo_name:30s}")
                sys.stderr.flush()

            sys.stderr.write("\n")

    out_f.close()
    print(f"\nSaved {out_path}", file=sys.stderr)


def bench_sssp(args: argparse.Namespace) -> None:
    if args.list:
        for name in ALL_SSSP_NAMES:
            print(name)
        sys.exit(0)

    selected: set[str] = set(ALL_SSSP_NAMES)
    if args.algos:
        selected = set(args.algos)
        unknown = selected - set(ALL_SSSP_NAMES)
        if unknown:
            print(f"Unknown algorithms: {', '.join(sorted(unknown))}", file=sys.stderr)
            print("Use --list to see names.", file=sys.stderr)
            sys.exit(1)

    map_files = sorted(MAPS_DIR.glob("*.map26"))
    if not map_files:
        print(f"No .map26 files in {MAPS_DIR}", file=sys.stderr)
        sys.exit(1)

    n_sources: int = args.samples
    times: dict[str, dict[str, list[float]]] = {}
    opt_ratios: dict[str, dict[str, list[float]]] = {}

    for mf in map_files:
        m = load_map(mf)
        map_name = mf.stem
        tiles: list[int] = [tile for row in m.rows for tile in row.tiles]
        w, h = m.width, m.height
        n = w * h
        nb = build_nb(w, h)

        cost = build_cost(tiles, n)
        passable = [i for i in range(n) if cost[i] < INF]
        if not passable:
            continue

        rng = random.Random(SEED)
        sources = [rng.choice(passable) for _ in range(n_sources)]

        for scenario in SCENARIOS:
            cost = build_cost(tiles, n)
            if scenario == "with_roads":
                passable = [i for i in range(n) if cost[i] < INF]
                place_roads(tiles, cost, nb, passable)

            pnb = build_pnb(nb, cost)
            pnbc = build_pnbc(nb, cost)
            pnb1, pnb3 = build_pnb_dual(nb, cost)
            pnb_push, pnb_set = build_pnb_navbfs(w, h, cost)
            pnb_push_dij, pnb_set_dij = build_pnb_navdijkstra(w, h, cost)
            pnb_push_dij_c, pnb_set_dij_c = build_pnbc_navdijkstra(w, h, cost)
            pnb_dir = build_pnb_dir(w, h, cost)
            pnb_by_offset = build_pnb_by_offset(w, h, cost)
            dir_of_offset = build_dir_of_offset(w)
            passable = [i for i in range(n) if cost[i] < INF]

            label = f"{map_name}/{scenario}"
            sys.stderr.write(f"\r{label:40s}")
            sys.stderr.flush()

            goals = [rng.choice(passable) for _ in range(n_sources)]

            ref_dists: list[list[int]] = [
                reference_dist(n, cost, pnb, start) for start in sources
            ]

            algos = _build_sssp_algos(
                n,
                cost,
                pnb,
                pnbc,
                pnb1,
                pnb3,
                pnb_push,
                pnb_set,
                pnb_push_dij,
                pnb_set_dij,
                pnb_push_dij_c,
                pnb_set_dij_c,
                pnb_dir,
                pnb_by_offset,
                dir_of_offset,
                w,
                selected,
            )

            for algo_name, algo_fn in algos:
                for idx, (start, _goal) in enumerate(zip(sources, goals, strict=True)):
                    t0 = time.perf_counter()
                    result = algo_fn(start)
                    us = (time.perf_counter() - t0) * 1e6
                    times.setdefault(algo_name, {}).setdefault(scenario, []).append(us)

                    ref = ref_dists[idx]
                    hop_algos = (
                        "bfs",
                        "bfs-level",
                        "bfs-buckets",
                        "bfs-skip",
                        "bfs-skip-level",
                        "bfs-jps",
                        "bfs-jps-list",
                        "bfs-jps-list-dbl",
                        "bfs-jps-list-merge",
                        "bfs-jps-list-merge-off",
                        "bfs-jps-list-defer",
                        "bfs-jps-list-off",
                    )
                    exact_algos = ("bfs-expand",)
                    if (
                        algo_name in (*hop_algos, *exact_algos)
                        and scenario != "no_roads"
                    ):
                        got = result
                        if algo_name in hop_algos:
                            got = [d * CE if d < INF else INF for d in result]
                    else:
                        got = result
                        if algo_name in hop_algos:
                            got = [d * CE if d < INF else INF for d in result]
                        for i in range(n):
                            if got[i] != ref[i]:
                                x, y = i % w, i // w
                                print(
                                    f"\nMISMATCH {algo_name} on "
                                    f"{map_name}/{scenario} "
                                    f"src={start} tile=({x},{y}) "
                                    f"got={got[i]} ref={ref[i]}",
                                    file=sys.stderr,
                                )
                                sys.exit(1)

                    worst_ratio = 1.0
                    for i in range(n):
                        if ref[i] < INF and ref[i] > 0 and got[i] < INF:
                            ratio = got[i] / ref[i]
                            worst_ratio = max(worst_ratio, ratio)
                    opt_ratios.setdefault(algo_name, {}).setdefault(
                        scenario, []
                    ).append(worst_ratio)

    sys.stderr.write("\r" + " " * 60 + "\r")

    for scenario in SCENARIOS:
        print(f"\n  {scenario.upper()}")
        print(
            f"  {'Algorithm':<28s} {'t_mean':>8s} {'t_p50':>8s} {'t_p90':>8s} {'t_p99':>8s} {'t_p100':>8s} {'o_p50':>7s} {'o_p99':>7s} {'o_p100':>7s}"
        )
        print(f"  {'-' * 95}")
        all_names = list(times.keys())
        seen: set[str] = set()
        for algo_name in all_names:
            if algo_name in seen:
                continue
            seen.add(algo_name)
            ts = sorted(times.get(algo_name, {}).get(scenario, []))
            if not ts:
                continue
            nt = len(ts)
            t_mean = sum(ts) / nt
            t50 = ts[nt // 2]
            t90 = ts[int(nt * 0.9)]
            t99 = ts[int(nt * 0.99)]
            t100 = ts[-1]
            os = sorted(opt_ratios.get(algo_name, {}).get(scenario, []))
            if os:
                no = len(os)
                o50 = os[no // 2]
                o99 = os[int(no * 0.99)]
                o100 = os[-1]
                opt_str = f" {o50:>7.3f} {o99:>7.3f} {o100:>7.3f}"
            else:
                opt_str = ""
            print(
                f"  {algo_name:<28s} {t_mean:>7.0f}us {t50:>7.0f}us {t90:>7.0f}us {t99:>7.0f}us {t100:>7.0f}us{opt_str}",
            )


type Row = dict[str, str]


def _load_csv(path: Path) -> list[Row]:
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        print("Run `bench-nav spsp` first.", file=sys.stderr)
        sys.exit(1)
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def _quantile(vals: list[float], q: float) -> float:
    if not vals:
        return 0.0
    vals.sort()
    idx = q * (len(vals) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(vals) - 1)
    frac = idx - lo
    return vals[lo] * (1 - frac) + vals[hi] * frac


def _safe_floats(rows: list[Row], key: str) -> list[float]:
    out: list[float] = []
    for r in rows:
        v = r.get(key, "")
        if v != "":
            with contextlib.suppress(ValueError):
                out.append(float(v))
    return out


def _print_scenario(rows: list[Row], scenario: str) -> None:
    algos: list[str] = list(dict.fromkeys(r["algo"] for r in rows))

    hdr = (
        f"{'Algorithm':<50}"
        f" {'t_p50':>7} {'t_p99':>7} {'t_p100':>7}"
        f" {'o_p50':>7} {'o_p99':>7} {'o_p100':>7}"
        f" {'reach%':>7} {'1st_mv%':>7}"
    )
    print(f"\n  {scenario.upper()}")
    print(hdr)
    print("-" * len(hdr))

    for algo in algos:
        ad = [r for r in rows if r["algo"] == algo]
        times_list = _safe_floats(ad, "time_us")
        reachable = [r for r in ad if r.get("reachable") == "1"]
        opts = _safe_floats(reachable, "opt_ratio")
        n_reached = sum(1 for r in reachable if r.get("reached_goal") == "1")
        n_reachable = len(reachable)
        fm = _safe_floats(reachable, "first_move_correct")

        t50 = _quantile(times_list, 0.5)
        t99 = _quantile(times_list, 0.99)
        t100 = max(times_list) if times_list else 0.0
        o50 = _quantile(opts, 0.5)
        o99 = _quantile(opts, 0.99)
        o100 = max(opts) if opts else 0.0
        reach_pct = 100 * n_reached / n_reachable if n_reachable > 0 else 0.0
        fm_pct = 100 * sum(fm) / len(fm) if fm else 0.0

        print(
            f"{algo:<50}"
            f" {t50:>7.0f} {t99:>7.0f} {t100:>7.0f}"
            f" {o50:>7.3f} {o99:>7.3f} {o100:>7.3f}"
            f" {reach_pct:>6.1f}% {fm_pct:>6.1f}%",
        )


def bench_table(args: argparse.Namespace) -> None:
    rows = _load_csv(args.csv)
    scenarios: list[str] = sorted({r["scenario"] for r in rows})
    for scenario in scenarios:
        _print_scenario([r for r in rows if r["scenario"] == scenario], scenario)


ALGO_CLASS_COLORS: dict[str, str] = {
    "astar-heap-cheb": "#4682b4",
    "astar-dial-cheb": "#e07020",
    "astar-heap-apsp": "#2ca02c",
    "bfs": "#d62728",
    "bfs-roadopt": "#b22222",
    "bibfs": "#ff6961",
    "gbfs": "#9467bd",
    "dijkstra-heap": "#8c564b",
    "dijkstra-dial": "#e377c2",
    "hpastar": "#7f7f7f",
    "biastar-dial-cheb": "#9b59b6",
    "biastar-dial-cheb-ft": "#e74c3c",
}


def _algo_class(name: str) -> str:
    for prefix in ALGO_CLASS_COLORS:
        if name.startswith(prefix):
            return prefix
    return name


def _algo_color(name: str) -> str:
    return ALGO_CLASS_COLORS.get(_algo_class(name), "#333333")


def bench_plot(args: argparse.Namespace) -> None:
    all_rows = _load_csv(args.csv)
    scenarios: list[str] = sorted({r["scenario"] for r in all_rows})
    algos: list[str] = list(dict.fromkeys(r["algo"] for r in all_rows))
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

    for start, scenario in enumerate(scenarios):
        sd = [r for r in all_rows if r["scenario"] == scenario]
        col_base = start * cols_per_scenario

        time_data: list[list[float]] = []
        opt_data: list[list[float]] = []
        reach_pcts: list[float] = []
        fm_pcts: list[float] = []

        for algo in algos:
            ad = [r for r in sd if r["algo"] == algo]
            times_list = _safe_floats(ad, "time_us")
            time_data.append(times_list or [0.0])

            reachable = [r for r in ad if r.get("reachable") == "1"]
            opts = _safe_floats(reachable, "opt_ratio")
            opt_data.append(opts or [1.0])

            n_reachable = len(reachable)
            n_found = sum(1 for r in reachable if r.get("reached_goal") == "1")
            reach_pcts.append(100 * n_found / n_reachable if n_reachable > 0 else 0.0)

            fm = _safe_floats(reachable, "first_move_correct")
            fm_pcts.append(100 * sum(fm) / len(fm) if fm else 0.0)

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
        if start == 0:
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
    out = Path("bench_nav.png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {out}", file=sys.stderr)
