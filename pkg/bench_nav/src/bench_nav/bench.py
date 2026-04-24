from __future__ import annotations

import csv as _csv
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

from bench_nav import mpsp, spsp, sssp, stepped
from bench_nav.common import INF, MAPS_DIR, SEED
from bench_nav.precomputation import build_cost, load_map, place_roads
from bench_nav.precomputation import build_nb as build_nb_fn
from bench_nav.queries import multi_waypoint_queries, spsp_queries, sssp_queries
from bench_nav.report import (
    SpspRow,
    SsspRow,
    print_spsp_table,
    print_sssp_table,
    row_from_spsp,
    row_from_sssp,
    write_spsp_csv,
    write_sssp_csv,
)
from bench_nav.runner import (
    DEFAULT_CFG,
    MapInput,
    build_context,
    first_moves_for,
    run_journey,
    run_sssp,
    run_stepped,
)
from bench_nav.types import (
    AlgoName,
    Mpsp,
    Precomp,
    Scenario,
    Spsp,
    Sssp,
    Stepped,
)
from bench_nav.validate import dijkstra_from

if TYPE_CHECKING:
    import argparse
    from collections.abc import Iterable

DEFAULT_N_QUERIES: Final = 1000


def _load_map_inputs() -> list[MapInput]:
    files = sorted(MAPS_DIR.glob("*.map26"))
    if not files:
        print(f"No .map26 files in {MAPS_DIR}", file=sys.stderr)
        sys.exit(1)
    out: list[MapInput] = []
    for mf in files:
        m = load_map(mf)
        tiles: list[int] = [t for row in m.rows for t in row.tiles]
        n = m.width * m.height
        out.append(
            MapInput(
                name=mf.stem,
                w=m.width,
                h=m.height,
                n=n,
                tiles=tiles,
                cost=build_cost(tiles, n),
            )
        )
    return out


def _apply_scenario(m: MapInput, sc: Scenario) -> MapInput:
    cost = list(m.cost)
    if sc is Scenario.WITH_ROADS:
        nb = build_nb_fn(m.w, m.h)
        passable = [i for i in range(m.n) if cost[i] < INF]
        place_roads(m.tiles, cost, nb, passable)
    return MapInput(name=m.name, w=m.w, h=m.h, n=m.n, tiles=m.tiles, cost=cost)


def _filter_algos[A: type[Spsp | Mpsp | Sssp | Stepped]](
    all_algos: tuple[A, ...], names: list[str] | None
) -> tuple[A, ...]:
    if not names:
        return all_algos
    wanted = {AlgoName(n) for n in names}
    filtered = tuple(a for a in all_algos if a.NAME in wanted)
    missing = wanted - {a.NAME for a in filtered}
    if missing:
        print(f"Unknown algos: {sorted(missing)}", file=sys.stderr)
        sys.exit(1)
    return filtered


def _required_precomps(
    algos: Iterable[type[Spsp | Mpsp | Sssp | Stepped]],
) -> frozenset[Precomp[object]]:
    required: set[Precomp[object]] = set()
    for a in algos:
        required |= a.REQUIRES
    return frozenset(required)


def _passable(cost: list[int]) -> list[int]:
    return [i for i, c in enumerate(cost) if c < INF]


def _run_plan_bench(
    all_algos: tuple[type[Spsp], ...] | tuple[type[Mpsp], ...],
    out_path: Path,
    args: argparse.Namespace,
) -> None:
    if args.list:
        for a in all_algos:
            print(a.NAME)
        return

    algos = _filter_algos(all_algos, args.algos)
    required = _required_precomps(algos)
    n_queries: int = args.samples
    n_waypoints: int = args.waypoints

    rows: list[SpspRow] = []
    maps = _load_map_inputs()
    for raw in maps:
        for sc in Scenario:
            m = _apply_scenario(raw, sc)
            ctx, gt = build_context(m, required)
            passable = _passable(gt.cost)
            if not passable:
                continue
            if n_waypoints <= 1:
                queries = spsp_queries(passable, n_queries, SEED)
            else:
                queries = multi_waypoint_queries(passable, n_queries, n_waypoints, SEED)
            first_moves_cache: dict[tuple[int, int], set[int]] = {}
            dist_cache: dict[int, list[int]] = {}
            for a in algos:
                prefix = f"{m.name:24s} {sc.value:11s} {a.NAME:30s}"
                sys.stderr.write(f"\r{prefix}")
                sys.stderr.flush()
                finder = a(ctx)
                for q in queries:
                    if q.start not in dist_cache:
                        dist_cache[q.start] = dijkstra_from(gt, q.start)
                    dist = dist_cache[q.start]
                    key = (q.start, q.goals[0])
                    if key not in first_moves_cache:
                        first_moves_cache[key] = first_moves_for(
                            gt, q.start, q.goals[0], dist
                        )
                    res = run_journey(
                        finder,
                        str(a.NAME),
                        ctx,
                        gt,
                        q,
                        DEFAULT_CFG,
                        m.name,
                        dist,
                        first_moves_cache[key],
                    )
                    rows.append(
                        row_from_spsp(
                            a.NAME,
                            sc,
                            m.name,
                            q.start,
                            q.goals[-1],
                            len(q.goals),
                            res,
                        )
                    )
            sys.stderr.write("\n")

    write_spsp_csv(rows, out_path)
    print(f"wrote {out_path}", file=sys.stderr)


def bench_spsp(args: argparse.Namespace) -> None:
    _run_plan_bench(spsp.ALGOS, Path("bench_nav_spsp.csv"), args)


def bench_mpsp(args: argparse.Namespace) -> None:
    _run_plan_bench(mpsp.ALGOS, Path("bench_nav_mpsp.csv"), args)


def bench_stepped(args: argparse.Namespace) -> None:
    if args.list:
        for a in stepped.ALGOS:
            print(a.NAME)
        return

    algos = _filter_algos(stepped.ALGOS, args.algos)
    required = _required_precomps(algos)
    n_queries: int = args.samples

    rows: list[SpspRow] = []
    for raw in _load_map_inputs():
        for sc in Scenario:
            m = _apply_scenario(raw, sc)
            ctx, gt = build_context(m, required)
            passable = _passable(gt.cost)
            if not passable:
                continue
            queries = spsp_queries(passable, n_queries, SEED)
            first_moves_cache: dict[tuple[int, int], set[int]] = {}
            dist_cache: dict[int, list[int]] = {}
            for a in algos:
                prefix = f"{m.name:24s} {sc.value:11s} {a.NAME:30s}"
                sys.stderr.write(f"\r{prefix}")
                sys.stderr.flush()
                stepper = a(ctx)
                for q in queries:
                    if q.start not in dist_cache:
                        dist_cache[q.start] = dijkstra_from(gt, q.start)
                    dist = dist_cache[q.start]
                    key = (q.start, q.goals[0])
                    if key not in first_moves_cache:
                        first_moves_cache[key] = first_moves_for(
                            gt, q.start, q.goals[0], dist
                        )
                    res = run_stepped(
                        stepper, ctx, gt, q, DEFAULT_CFG, dist, first_moves_cache[key]
                    )
                    rows.append(
                        row_from_spsp(
                            a.NAME,
                            sc,
                            m.name,
                            q.start,
                            q.goals[-1],
                            len(q.goals),
                            res,
                        )
                    )
            sys.stderr.write("\n")

    out = Path("bench_nav_stepped.csv")
    write_spsp_csv(rows, out)
    print(f"wrote {out}", file=sys.stderr)


def bench_sssp(args: argparse.Namespace) -> None:
    if args.list:
        for a in sssp.ALGOS:
            print(a.NAME)
        return

    algos = _filter_algos(sssp.ALGOS, args.algos)
    required = _required_precomps(algos)
    n_queries: int = args.samples

    rows: list[SsspRow] = []
    for raw in _load_map_inputs():
        for sc in Scenario:
            m = _apply_scenario(raw, sc)
            ctx, gt = build_context(m, required)
            passable = _passable(gt.cost)
            if not passable:
                continue
            queries = sssp_queries(passable, n_queries, SEED)
            for a in algos:
                prefix = f"{m.name:24s} {sc.value:11s} {a.NAME:30s}"
                sys.stderr.write(f"\r{prefix}")
                sys.stderr.flush()
                solver = a(ctx)
                for q in queries:
                    res = run_sssp(solver, a.UNIT, ctx, gt, q, DEFAULT_CFG)
                    rows.append(row_from_sssp(a.NAME, sc, m.name, q.start, res))
            sys.stderr.write("\n")

    out = Path("bench_nav_sssp.csv")
    write_sssp_csv(rows, out)
    print(f"wrote {out}", file=sys.stderr)


def bench_table_spsp(args: argparse.Namespace) -> None:
    with args.csv.open(newline="") as f:
        rows = [_parse_spsp_row(r) for r in _csv.DictReader(f)]
    print_spsp_table(rows)


def bench_table_sssp(args: argparse.Namespace) -> None:
    with args.csv.open(newline="") as f:
        rows = [_parse_sssp_row(r) for r in _csv.DictReader(f)]
    print_sssp_table(rows)


def _parse_spsp_row(r: dict[str, str]) -> SpspRow:
    def opt_float(key: str) -> float | None:
        v = r.get(key, "")
        return float(v) if v else None

    def opt_bool(key: str) -> bool | None:
        v = r.get(key, "")
        if v == "":
            return None
        return v == "1"

    return SpspRow(
        algo=AlgoName(r["algo"]),
        scenario=Scenario(r["scenario"]),
        map=r["map"],
        start=int(r["start"]),
        goal=int(r["goal"]),
        n_goals=int(r["n_goals"]),
        total_time_us=float(r["total_time_us"]),
        reached=r["reached"] == "1",
        ref_reachable=r["ref_reachable"] == "1",
        opt_ratio=opt_float("opt_ratio"),
        first_move_correct=opt_bool("first_move_correct"),
        cost_walked=int(r["cost_walked"]),
        steps_taken=int(r["steps_taken"]),
        tiles_revealed=int(r["tiles_revealed"]),
    )


def _parse_sssp_row(r: dict[str, str]) -> SsspRow:
    return SsspRow(
        algo=AlgoName(r["algo"]),
        scenario=Scenario(r["scenario"]),
        map=r["map"],
        start=int(r["start"]),
        time_us=float(r["time_us"]),
        exact=r["exact"] == "1",
        worst_ratio=float(r["worst_ratio"]),
    )
