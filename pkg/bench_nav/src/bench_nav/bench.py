from __future__ import annotations

import contextlib
import csv
import gc
import random
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt

from bench_nav.common import CE, INF, MAPS_DIR, SCENARIOS, SEED, Path_, bfs_dist
from bench_nav.map_data import (
    build_cost,
    build_nb,
    build_pnb,
    build_pnb_dual,
    build_pnb_navbfs,
    build_pnbc,
    load_map,
    place_roads,
)
from bench_nav.reference import (
    dijkstra_full,
    optimal_first_moves,
    path_cost,
    reference_dist,
    validate_path,
)
from bench_nav.spsp.astar_dial_apsp import astar_dial_apsp
from bench_nav.spsp.astar_dial_bfs import astar_dial_bfs
from bench_nav.spsp.astar_dial_cheb import astar_dial_cheb
from bench_nav.spsp.astar_dial_cheb_bw_dijkstra import astar_dial_cheb_bw_dijkstra
from bench_nav.spsp.astar_heap_apsp import astar_heap_apsp
from bench_nav.spsp.astar_heap_cheb import astar_heap_cheb
from bench_nav.spsp.bfs import bfs
from bench_nav.spsp.bfs_expand import bfs_expand
from bench_nav.spsp.bfs_roadopt import bfs_roadopt
from bench_nav.spsp.biastar_dial_cheb import biastar_dial_cheb
from bench_nav.spsp.biastar_dial_cheb_ft import biastar_dial_cheb_ft
from bench_nav.spsp.bibfs import bibfs
from bench_nav.spsp.dijkstra_dial import dijkstra_dial
from bench_nav.spsp.dijkstra_dial_dual import dijkstra_dial_dual
from bench_nav.spsp.dijkstra_heap import dijkstra_heap
from bench_nav.spsp.gbfs import gbfs
from bench_nav.spsp.hpastar import hpastar, precompute_hpa
from bench_nav.spsp.navbfs import navbfs
from bench_nav.spsp.navbfs_noextract import navbfs_noextract
from bench_nav.spsp.precompute_apsp import precompute_apsp
from bench_nav.sssp.bfs import bfs as sssp_bfs
from bench_nav.sssp.bfs_expand import bfs_expand as sssp_bfs_expand
from bench_nav.sssp.dijkstra_dial import dijkstra_dial as sssp_dijkstra_dial
from bench_nav.sssp.dijkstra_dial_dual import (
    dijkstra_dial_dual as sssp_dijkstra_dial_dual,
)
from bench_nav.sssp.dijkstra_dial_flat import (
    dijkstra_dial_flat as sssp_dijkstra_dial_flat,
)
from bench_nav.sssp.dijkstra_dial_pnbc import (
    dijkstra_dial_pnbc as sssp_dijkstra_dial_pnbc,
)
from bench_nav.sssp.dijkstra_dial_unrolled import (
    dijkstra_dial_unrolled as sssp_dijkstra_dial_unrolled,
)
from bench_nav.sssp.dijkstra_heap import dijkstra_heap as sssp_dijkstra_heap

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
    selected: set[str] | None,
) -> list[tuple[str, SpspFn]]:
    algos: list[tuple[str, SpspFn]] = []

    def add(name: str, fn: SpspFn) -> None:
        if selected is None or name in selected:
            algos.append((name, fn))

    add(
        "astar-heap-cheb",
        lambda start, goal: astar_heap_cheb(w, n, cost, pnb, start, goal),
    )
    add(
        "astar-dial-cheb",
        lambda start, goal: astar_dial_cheb(w, n, cost, pnb, start, goal),
    )

    if (
        selected is None
        or "astar-heap-apsp" in selected
        or "astar-dial-apsp" in selected
    ):
        apsp = precompute_apsp(n, cost, pnb)
        add(
            "astar-heap-apsp",
            lambda start, goal: astar_heap_apsp(n, cost, pnb, apsp, start, goal),
        )
        add(
            "astar-dial-apsp",
            lambda start, goal: astar_dial_apsp(n, cost, pnb, apsp, start, goal),
        )

    add("bfs", lambda start, goal: bfs(n, pnb, start, goal))
    add("bfs-expand", lambda start, goal: bfs_expand(n, cost, pnb, start, goal))
    add("bfs-roadopt", lambda start, goal: bfs_roadopt(n, cost, pnb, start, goal))
    add(
        "navbfs",
        lambda start, goal: navbfs(n, cost, pnb, pnb_push, pnb_set, start, goal),
    )
    add(
        "navbfs-noextract",
        lambda start, goal: navbfs_noextract(n, pnb_push, pnb_set, start, goal),
    )
    add("bibfs", lambda start, goal: bibfs(n, pnb, start, goal))
    add("gbfs", lambda start, goal: gbfs(w, n, pnb, start, goal))
    add(
        "dijkstra-heap",
        lambda start, goal: dijkstra_heap(n, cost, pnb, start, goal),
    )
    add(
        "dijkstra-dial",
        lambda start, goal: dijkstra_dial(n, cost, pnb, start, goal),
    )
    add(
        "dijkstra-dial-dual",
        lambda start, goal: dijkstra_dial_dual(n, cost, pnb, pnb1, pnb3, start, goal),
    )

    if selected is None or "hpastar" in selected:
        hpa_graph = precompute_hpa(w, h, cost)
        add("hpastar", lambda start, goal: hpastar(w, hpa_graph, start, goal))

    if selected is None or "astar-dial-bfs" in selected:
        bfs_h_cache: dict[int, list[int]] = {}

        def _astar_dial_bfs(start: int, goal: int) -> Path_:
            if start not in bfs_h_cache:
                bfs_h_cache[start] = bfs_dist(n, pnb, start)
            return astar_dial_bfs(n, cost, pnb, bfs_h_cache[start], start, goal)

        add("astar-dial-bfs", _astar_dial_bfs)

    add(
        "biastar-dial-cheb",
        lambda start, goal: biastar_dial_cheb(w, n, cost, pnb, start, goal),
    )
    add(
        "biastar-dial-cheb-ft",
        lambda start, goal: biastar_dial_cheb_ft(w, n, cost, pnb, start, goal),
    )
    add(
        "astar-cheb+bw-dijkstra",
        lambda start, goal: astar_dial_cheb_bw_dijkstra(w, n, cost, pnb, start, goal),
    )

    return algos


def _build_sssp_algos(
    n: int,
    cost: list[int],
    pnb: list[list[int]],
    pnbc: list[list[tuple[int, int]]],
    pnb1: list[list[int]],
    pnb3: list[list[int]],
    selected: set[str] | None,
) -> list[tuple[str, SsspFn]]:
    algos: list[tuple[str, SsspFn]] = []

    def add(name: str, fn: SsspFn) -> None:
        if selected is None or name in selected:
            algos.append((name, fn))

    add("bfs", lambda start: sssp_bfs(n, pnb, start))
    add("bfs-expand", lambda start: sssp_bfs_expand(n, cost, pnb, start))
    add("dijkstra-heap", lambda start: sssp_dijkstra_heap(n, cost, pnb, start))
    add("dijkstra-dial", lambda start: sssp_dijkstra_dial(n, cost, pnb, start))
    add("dijkstra-dial-pnbc", lambda start: sssp_dijkstra_dial_pnbc(n, pnbc, start))
    add(
        "dijkstra-dial-flat",
        lambda start: sssp_dijkstra_dial_flat(n, cost, pnb, start),
    )
    add(
        "dijkstra-dial-dual",
        lambda start: sssp_dijkstra_dial_dual(n, pnb1, pnb3, start),
    )
    add(
        "dijkstra-dial-unrolled",
        lambda start: sssp_dijkstra_dial_unrolled(n, cost, pnb, start),
    )

    return algos


ALL_SPSP_NAMES: list[str] = [
    "astar-heap-cheb",
    "astar-dial-cheb",
    "astar-heap-apsp",
    "astar-dial-apsp",
    "bfs",
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
    "astar-dial-bfs",
    "biastar-dial-cheb",
    "biastar-dial-cheb-ft",
    "astar-cheb+bw-dijkstra",
]

ALL_SSSP_NAMES: list[str] = [
    "bfs",
    "bfs-expand",
    "dijkstra-heap",
    "dijkstra-dial",
    "dijkstra-dial-pnbc",
    "dijkstra-dial-flat",
    "dijkstra-dial-dual",
    "dijkstra-dial-unrolled",
]


def bench_spsp(args: argparse.Namespace) -> None:
    if args.list:
        for name in ALL_SPSP_NAMES:
            print(name)
        sys.exit(0)

    selected: set[str] | None = None
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

            algos = _build_spsp_algos(
                w, h, n, cost, pnb, pnb1, pnb3, pnb_push, pnb_set, selected
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

    selected: set[str] | None = None
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
            passable = [i for i in range(n) if cost[i] < INF]

            label = f"{map_name}/{scenario}"
            sys.stderr.write(f"\r{label:40s}")
            sys.stderr.flush()

            goals = [rng.choice(passable) for _ in range(n_sources)]

            ref_dists: list[list[int]] = [
                reference_dist(n, cost, pnb, start) for start in sources
            ]

            algos = _build_sssp_algos(n, cost, pnb, pnbc, pnb1, pnb3, selected)

            for algo_name, algo_fn in algos:
                gc.disable()
                for idx, (start, _goal) in enumerate(zip(sources, goals, strict=True)):
                    t0 = time.perf_counter()
                    result = algo_fn(start)
                    us = (time.perf_counter() - t0) * 1e6
                    times.setdefault(algo_name, {}).setdefault(scenario, []).append(us)

                    if algo_name in ("bfs", "bfs-expand") and scenario != "no_roads":
                        pass
                    else:
                        got = result
                        if algo_name == "bfs":
                            got = [d * CE if d < INF else INF for d in result]
                        ref = ref_dists[idx]
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
                gc.enable()

    sys.stderr.write("\r" + " " * 60 + "\r")

    for scenario in SCENARIOS:
        print(f"\n  {scenario.upper()}")
        print(f"  {'Algorithm':<24s} {'p50':>8s} {'p90':>8s} {'p99':>8s} {'p100':>8s}")
        print(f"  {'-' * 56}")
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
            p50 = ts[nt // 2]
            p90 = ts[int(nt * 0.9)]
            p99 = ts[int(nt * 0.99)]
            p100 = ts[-1]
            print(
                f"  {algo_name:<24s} {p50:>7.0f}us {p90:>7.0f}us {p99:>7.0f}us {p100:>7.0f}us",
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
