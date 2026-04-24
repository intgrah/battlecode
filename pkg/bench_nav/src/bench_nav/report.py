from __future__ import annotations

import csv
from dataclasses import dataclass, fields
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from bench_nav.types import AlgoName, Scenario, SpspResult, SsspResult


@dataclass(frozen=True)
class SpspRow:
    algo: AlgoName
    scenario: Scenario
    map: str
    start: int
    goal: int
    n_goals: int
    total_time_us: float
    reached: bool
    ref_reachable: bool
    opt_ratio: float | None
    first_move_correct: bool | None
    cost_walked: int
    steps_taken: int
    tiles_revealed: int


@dataclass(frozen=True)
class SsspRow:
    algo: AlgoName
    scenario: Scenario
    map: str
    start: int
    time_us: float
    exact: bool
    worst_ratio: float


def row_from_spsp(
    algo: AlgoName,
    scenario: Scenario,
    map_name: str,
    start: int,
    goal: int,
    n_goals: int,
    result: SpspResult,
) -> SpspRow:
    return SpspRow(
        algo=algo,
        scenario=scenario,
        map=map_name,
        start=start,
        goal=goal,
        n_goals=n_goals,
        total_time_us=result.total_time_us,
        reached=result.reached,
        ref_reachable=result.ref_reachable,
        opt_ratio=result.opt_ratio,
        first_move_correct=result.first_move_correct,
        cost_walked=result.walk.cost_walked,
        steps_taken=result.walk.steps_taken,
        tiles_revealed=result.walk.tiles_revealed,
    )


def row_from_sssp(
    algo: AlgoName,
    scenario: Scenario,
    map_name: str,
    start: int,
    result: SsspResult,
) -> SsspRow:
    return SsspRow(
        algo=algo,
        scenario=scenario,
        map=map_name,
        start=start,
        time_us=result.time_us,
        exact=result.exact,
        worst_ratio=result.worst_ratio,
    )


def _serialize(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def write_spsp_csv(rows: list[SpspRow], path: Path) -> None:
    field_names = [f.name for f in fields(SpspRow)]
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(field_names)
        for r in rows:
            w.writerow(_serialize(getattr(r, name)) for name in field_names)


def write_sssp_csv(rows: list[SsspRow], path: Path) -> None:
    field_names = [f.name for f in fields(SsspRow)]
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(field_names)
        for r in rows:
            w.writerow(_serialize(getattr(r, name)) for name in field_names)


def _quantile(vals: list[float], q: float) -> float:
    if not vals:
        return 0.0
    vals = sorted(vals)
    idx = q * (len(vals) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(vals) - 1)
    frac = idx - lo
    return vals[lo] * (1 - frac) + vals[hi] * frac


def print_spsp_table(rows: list[SpspRow]) -> None:
    scenarios = sorted({r.scenario for r in rows}, key=lambda s: s.value)
    for sc in scenarios:
        sd = [r for r in rows if r.scenario is sc]
        print(f"\n  {sc.value.upper()}")
        print(
            f"  {'algo':<35s}"
            f" {'t_p50':>8s} {'t_p99':>8s} {'t_p100':>8s}"
            f" {'o_p50':>7s} {'o_p99':>7s} {'o_p100':>7s}"
            f" {'reach%':>7s} {'1st_mv%':>7s}"
        )
        print(f"  {'-' * 110}")
        algos = list(dict.fromkeys(r.algo for r in sd))
        for algo in algos:
            ad = [r for r in sd if r.algo == algo]
            times = [r.total_time_us for r in ad]
            opts = [r.opt_ratio for r in ad if r.opt_ratio is not None]
            reached = [r for r in ad if r.reached]
            fms = [r.first_move_correct for r in ad if r.first_move_correct is not None]
            t50 = _quantile(times, 0.5)
            t99 = _quantile(times, 0.99)
            t100 = max(times) if times else 0.0
            o50 = _quantile(opts, 0.5)
            o99 = _quantile(opts, 0.99)
            o100 = max(opts) if opts else 0.0
            ref_ok = [r for r in ad if r.ref_reachable]
            reach_pct = 100 * len(reached) / len(ref_ok) if ref_ok else 0.0
            fm_pct = 100 * sum(1 for fm in fms if fm) / len(fms) if fms else 0.0
            print(
                f"  {algo:<35s}"
                f" {t50:>7.0f}us {t99:>7.0f}us {t100:>7.0f}us"
                f" {o50:>7.3f} {o99:>7.3f} {o100:>7.3f}"
                f" {reach_pct:>6.1f}% {fm_pct:>6.1f}%",
            )


def print_sssp_table(rows: list[SsspRow]) -> None:
    scenarios = sorted({r.scenario for r in rows}, key=lambda s: s.value)
    for sc in scenarios:
        sd = [r for r in rows if r.scenario is sc]
        print(f"\n  {sc.value.upper()}")
        print(
            f"  {'algo':<35s}"
            f" {'t_p50':>8s} {'t_p99':>8s} {'t_p100':>8s}"
            f" {'o_p50':>7s} {'o_p100':>7s} {'exact%':>7s}"
        )
        print(f"  {'-' * 90}")
        algos = list(dict.fromkeys(r.algo for r in sd))
        for algo in algos:
            ad = [r for r in sd if r.algo == algo]
            times = [r.time_us for r in ad]
            ratios = [r.worst_ratio for r in ad]
            t50 = _quantile(times, 0.5)
            t99 = _quantile(times, 0.99)
            t100 = max(times) if times else 0.0
            o50 = _quantile(ratios, 0.5)
            o100 = max(ratios) if ratios else 0.0
            exact_pct = 100 * sum(1 for r in ad if r.exact) / len(ad) if ad else 0.0
            print(
                f"  {algo:<35s}"
                f" {t50:>7.0f}us {t99:>7.0f}us {t100:>7.0f}us"
                f" {o50:>7.3f} {o100:>7.3f} {exact_pct:>6.1f}%",
            )
