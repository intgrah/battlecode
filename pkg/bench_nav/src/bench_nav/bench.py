from __future__ import annotations

import csv
import gc
import random
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import pandas as pd

from bench_nav.common import CE, INF, MAPS_DIR, SCENARIOS, SEED
from bench_nav.map_data import MapData
from bench_nav.reference import (
    dijkstra_full,
    expanded_parent_to_dist,
    extract_path_from_dist,
    optimal_first_moves,
    parent_to_dist,
    path_cost,
    sssp_reference_dist,
    validate_path,
)
from bench_nav.registry import ALGOS, SSSP_ALGOS
from bench_nav.spsp.apsp import precompute_apsp
from bench_nav.spsp.astar import _bfs_dist
from bench_nav.spsp.hpastar import precompute_hpa

if TYPE_CHECKING:
    import argparse


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
    "si",
    "gi",
    "time_us",
    "reachable",
    "reached_goal",
    "opt_ratio",
    "first_move_correct",
]


def bench_spsp(args: argparse.Namespace) -> None:
    if args.list:
        for name, _, _ in ALGOS:
            print(name)
        sys.exit(0)

    if args.algos:
        algo_set = set(args.algos)
        known = {name for name, _, _ in ALGOS}
        unknown = algo_set - known
        if unknown:
            print(f"Unknown algorithms: {', '.join(sorted(unknown))}", file=sys.stderr)
            print("Use --list to see names.", file=sys.stderr)
            sys.exit(1)
        selected = [(name, fn, req) for name, fn, req in ALGOS if name in algo_set]
    else:
        selected = list(ALGOS)

    n_pairs: int = args.samples

    map_files = sorted(MAPS_DIR.glob("*.map26"))
    if not map_files:
        print(f"No .map26 files in {MAPS_DIR}", file=sys.stderr)
        sys.exit(1)

    n_maps = len(map_files)
    needs_apsp = any(req for _, _, req in selected)
    needs_hpa = any("hpa" in name for name, _, _ in selected)
    needs_bfs_h = any(name == "astar-dial-bfs" for name, _, _ in selected)
    n_algos = len(selected)
    n_scenarios = len(SCENARIOS)
    total_work = n_maps * n_scenarios * (n_algos + 1)
    done = 0

    out_path = Path("bench_nav.csv")
    out_f = out_path.open("w", newline="")
    writer = csv.DictWriter(out_f, fieldnames=CSV_FIELDS)
    writer.writeheader()

    hpa_precomp_times: list[float] = []

    for mf in map_files:
        md = MapData(mf)
        if not md.passable:
            done += n_scenarios * (n_algos + 1)
            progress_bar(done, total_work, prefix=f"{md.name:24s} ")
            continue

        rng = random.Random(SEED)
        pairs = [
            (rng.choice(md.passable), rng.choice(md.passable)) for _ in range(n_pairs)
        ]

        if needs_apsp:
            md.reset_cost_no_roads()
            precompute_apsp(md)

        for scenario in SCENARIOS:
            md.reset_cost_no_roads()
            if scenario == "with_roads":
                md.place_roads()

            prefix = f"{md.name:24s} {scenario:11s} "

            gt_cache: dict[int, list[int]] = {}
            first_moves_cache: dict[tuple[int, int], set[int]] = {}
            for si, gi in pairs:
                if si not in gt_cache:
                    gt_cache[si] = dijkstra_full(md, si)
                key = (si, gi)
                if key not in first_moves_cache:
                    first_moves_cache[key] = optimal_first_moves(
                        md,
                        si,
                        gi,
                        gt_cache[si],
                    )

            done += 1
            progress_bar(done, total_work, prefix=prefix)

            if needs_hpa:
                t0 = time.perf_counter()
                precompute_hpa(md)
                hpa_precomp_times.append((time.perf_counter() - t0) * 1e6)

            if needs_bfs_h:
                md.bfs_h_cache = {}
                for si, _ in pairs:
                    if si not in md.bfs_h_cache:
                        md.bfs_h_cache[si] = _bfs_dist(md.n, md.pnb, si)

            for algo_name, algo_fn, req_apsp in selected:
                if req_apsp and md.apsp is None and md.hpa_graph is None:
                    done += 1
                    progress_bar(done, total_work, prefix=prefix)
                    continue

                for si, gi in pairs:
                    gd = gt_cache[si][gi]
                    reachable = gd < INF

                    if not reachable:
                        t0 = time.perf_counter()
                        algo_fn(md, si, gi)
                        us = (time.perf_counter() - t0) * 1e6
                        row: dict[str, str | int] = {
                            "algo": algo_name,
                            "scenario": scenario,
                            "map": md.name,
                            "si": si,
                            "gi": gi,
                            "time_us": f"{us:.1f}",
                            "reachable": 0,
                            "reached_goal": "",
                            "opt_ratio": "",
                            "first_move_correct": "",
                        }
                        writer.writerow(row)
                        continue

                    if si == gi:
                        row = {
                            "algo": algo_name,
                            "scenario": scenario,
                            "map": md.name,
                            "si": si,
                            "gi": gi,
                            "time_us": "0.0",
                            "reachable": 1,
                            "reached_goal": 1,
                            "opt_ratio": "1.0",
                            "first_move_correct": 1,
                        }
                        writer.writerow(row)
                        continue

                    t0 = time.perf_counter()
                    path = algo_fn(md, si, gi)
                    us = (time.perf_counter() - t0) * 1e6

                    reached = 0
                    opt = ""
                    fm = 0
                    if path is not None and len(path) >= 1:
                        validate_path(md, path, si, algo_name)
                        pc = path_cost(md, path)
                        if path[-1] == gi and pc < INF:
                            reached = 1
                            opt = f"{pc / gd:.6f}"
                        fm_set = first_moves_cache[(si, gi)]
                        if len(path) >= 2 and path[1] in fm_set:
                            fm = 1

                    row = {
                        "algo": algo_name,
                        "scenario": scenario,
                        "map": md.name,
                        "si": si,
                        "gi": gi,
                        "time_us": f"{us:.1f}",
                        "reachable": 1,
                        "reached_goal": reached,
                        "opt_ratio": opt,
                        "first_move_correct": fm,
                    }
                    writer.writerow(row)

                done += 1
                progress_bar(done, total_work, prefix=prefix)

    if hpa_precomp_times:
        hpa_precomp_times.sort()
        hn = len(hpa_precomp_times)
        print(
            f"\nHPA* precomp: p50={hpa_precomp_times[hn // 2]:.0f}us"
            f" p100={hpa_precomp_times[-1]:.0f}us",
            file=sys.stderr,
        )

    out_f.close()
    print(f"\nSaved {out_path}", file=sys.stderr)


def bench_sssp(args: argparse.Namespace) -> None:
    if args.list:
        for name, _ in SSSP_ALGOS:
            print(name)
        sys.exit(0)

    if args.algos:
        algo_set = set(args.algos)
        known = {name for name, _ in SSSP_ALGOS}
        unknown = algo_set - known
        if unknown:
            print(f"Unknown algorithms: {', '.join(sorted(unknown))}", file=sys.stderr)
            print("Use --list to see names.", file=sys.stderr)
            sys.exit(1)
        selected = [(name, fn) for name, fn in SSSP_ALGOS if name in algo_set]
    else:
        selected = list(SSSP_ALGOS)

    map_files = sorted(MAPS_DIR.glob("*.map26"))
    if not map_files:
        print(f"No .map26 files in {MAPS_DIR}", file=sys.stderr)
        sys.exit(1)

    n_sources: int = args.samples
    times: dict[str, dict[str, list[float]]] = {name: {} for name, _ in selected}

    for mf in map_files:
        md = MapData(mf)
        if not md.passable:
            continue

        rng = random.Random(SEED)
        sources = [rng.choice(md.passable) for _ in range(n_sources)]

        for scenario in SCENARIOS:
            md.reset_cost_no_roads()
            if scenario == "with_roads":
                md.place_roads()

            label = f"{md.name}/{scenario}"
            sys.stderr.write(f"\r{label:40s}")
            sys.stderr.flush()

            goals = [rng.choice(md.passable) for _ in range(n_sources)]

            ref_dists: list[list[int]] = [sssp_reference_dist(md, si) for si in sources]

            for algo_name, algo_fn in selected:
                gc.disable()
                for idx, (si, gi) in enumerate(
                    zip(sources, goals, strict=True),
                ):
                    t0 = time.perf_counter()
                    result = algo_fn(md, si)
                    us = (time.perf_counter() - t0) * 1e6
                    times[algo_name].setdefault(scenario, []).append(us)
                    if algo_name == "dijkstra-dial-np":
                        t1 = time.perf_counter()
                        extract_path_from_dist(result, md.cost, md.pnb, si, gi)
                        ex_us = (time.perf_counter() - t1) * 1e6
                        times.setdefault("noparent+extract", {}).setdefault(
                            scenario,
                            [],
                        ).append(us + ex_us)
                        times.setdefault("extract only", {}).setdefault(
                            scenario,
                            [],
                        ).append(ex_us)

                    if algo_name == "bfs" and scenario != "no_roads":
                        pass
                    else:
                        if "-np" in algo_name:
                            got_dist = result
                        elif algo_name == "bfs-expand":
                            got_dist = expanded_parent_to_dist(result, md.n, si)
                        elif algo_name == "bfs":
                            got_dist = parent_to_dist(
                                result,
                                [CE] * md.n,
                                md.n,
                                si,
                            )
                        else:
                            got_dist = parent_to_dist(
                                result,
                                md.cost,
                                md.n,
                                si,
                            )

                        ref = ref_dists[idx]
                        for i in range(md.n):
                            if got_dist[i] != ref[i]:
                                x, y = i % md.w, i // md.w
                                print(
                                    f"\nMISMATCH {algo_name} on "
                                    f"{md.name}/{scenario} "
                                    f"src={si} tile=({x},{y}) "
                                    f"got={got_dist[i]} ref={ref[i]}",
                                    file=sys.stderr,
                                )
                                sys.exit(1)
                gc.enable()

    sys.stderr.write("\r" + " " * 60 + "\r")

    for scenario in SCENARIOS:
        print(f"\n  {scenario.upper()}")
        print(f"  {'Algorithm':<24s} {'p50':>8s} {'p90':>8s} {'p99':>8s} {'p100':>8s}")
        print(f"  {'-' * 56}")
        for algo_name in [n for n, _ in selected] + [
            "noparent+extract",
            "extract only",
        ]:
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


def _load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        print("Run `bench-nav spsp` first.", file=sys.stderr)
        sys.exit(1)
    return pd.read_csv(path)


def _print_scenario(df: pd.DataFrame, scenario: str) -> None:
    algos: list[str] = list(dict.fromkeys(df["algo"]))

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
        ad = df[df["algo"] == algo]
        times = ad["time_us"]
        reachable = ad[ad["reachable"] == 1]
        opts = pd.to_numeric(reachable["opt_ratio"], errors="coerce").dropna()
        n_reached = int(reachable["reached_goal"].sum()) if len(reachable) > 0 else 0
        n_reachable = len(reachable)
        fm = pd.to_numeric(reachable["first_move_correct"], errors="coerce").dropna()

        t50 = times.quantile(0.5) if len(times) > 0 else 0
        t99 = times.quantile(0.99) if len(times) > 0 else 0
        t100 = times.max() if len(times) > 0 else 0
        o50 = opts.quantile(0.5) if len(opts) > 0 else 0
        o99 = opts.quantile(0.99) if len(opts) > 0 else 0
        o100 = opts.max() if len(opts) > 0 else 0
        reach_pct = 100 * n_reached / n_reachable if n_reachable > 0 else 0
        fm_pct = 100 * fm.mean() if len(fm) > 0 else 0

        print(
            f"{algo:<50}"
            f" {t50:>7.0f} {t99:>7.0f} {t100:>7.0f}"
            f" {o50:>7.3f} {o99:>7.3f} {o100:>7.3f}"
            f" {reach_pct:>6.1f}% {fm_pct:>6.1f}%",
        )


def bench_table(args: argparse.Namespace) -> None:
    df = _load_csv(args.csv)
    scenarios: list[str] = sorted(df["scenario"].unique())
    for scenario in scenarios:
        _print_scenario(df[df["scenario"] == scenario], scenario)


ALGO_CLASS_COLORS: dict[str, str] = {
    "astar-heap-cheb1": "#4682b4",
    "astar-heap-cheb3": "#1e3a5f",
    "astar-dial-cheb1": "#e07020",
    "astar-dial-cheb3": "#8b4513",
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

    df = _load_csv(args.csv)
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
    out = Path("bench_nav.png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {out}", file=sys.stderr)
