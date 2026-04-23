from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Final

from bench_nav.common import INF
from bench_nav.precompute import COST, PNB, build_ctx, resolve
from bench_nav.sensor import Sensor
from bench_nav.types import (
    Precomp,
    PrecompCtx,
    SensorReading,
    SequentialQuery,
    SequentialSpspAlgo,
    SpspResult,
    SsspAlgo,
    SsspQuery,
    SsspResult,
    Walk,
)
from bench_nav.validate import (
    GroundTruth,
    check_sssp,
    dijkstra_from,
    optimal_first_moves,
    validate_path,
)


@dataclass(frozen=True)
class MapInput:
    name: str
    w: int
    h: int
    n: int
    tiles: list[int]
    cost: list[int]


@dataclass(frozen=True)
class RunCfg:
    step_budget_mult: int = 8
    hop_scale: int = 3


DEFAULT_CFG: Final[RunCfg] = RunCfg()


def build_context(
    m: MapInput, required: frozenset[Precomp[object]]
) -> tuple[PrecompCtx, GroundTruth]:
    order = resolve(required | {COST, PNB})
    ctx = build_ctx(m.w, m.h, m.tiles, m.cost, order)
    gt = GroundTruth(w=m.w, n=m.n, cost=ctx[COST], pnb=ctx[PNB])
    return ctx, gt


def run_sequential[S](
    algo: SequentialSpspAlgo[S],
    ctx: PrecompCtx,
    gt: GroundTruth,
    q: SequentialQuery,
    cfg: RunCfg,
    map_name: str,
    dist_from_start: list[int],
    first_moves_first_goal: set[int],
) -> SpspResult:
    sensor = Sensor(w=ctx.w, h=ctx.h, n=ctx.n, cost=gt.cost, vision_r2=q.vision_r2)
    reading = sensor.reveal(q.start)

    t0 = time.perf_counter_ns()
    state, plan = algo.init(ctx, reading, q.start, q.goals[0])
    step_times: list[float] = [(time.perf_counter_ns() - t0) / 1000.0]

    pos = q.start
    plan_idx = 0
    cost_walked = 0
    steps = 0
    budget = cfg.step_budget_mult * ctx.n
    reached_all = True
    first_move_correct: bool | None = None

    if plan is not None and len(plan) >= 2 and first_moves_first_goal:
        first_move_correct = plan[1] in first_moves_first_goal

    for goal_idx, goal in enumerate(q.goals):
        if goal_idx > 0:
            t0 = time.perf_counter_ns()
            state, plan = algo.step(state, _empty_reading(), pos, goal)
            step_times.append((time.perf_counter_ns() - t0) / 1000.0)
            plan_idx = 0

        while pos != goal:
            if steps >= budget:
                reached_all = False
                break

            if plan is None or plan_idx + 1 >= len(plan):
                reached_all = False
                break

            if not validate_path(gt, plan, plan[0], str(algo.name), map_name):
                reached_all = False
                break

            next_pos = plan[plan_idx + 1]
            if gt.cost[next_pos] >= INF:
                reached_all = False
                break

            cost_walked += gt.cost[next_pos]
            pos = next_pos
            plan_idx += 1
            steps += 1

            reading = sensor.reveal(pos)
            if reading.newly_visible:
                t0 = time.perf_counter_ns()
                state, plan = algo.step(state, reading, pos, goal)
                step_times.append((time.perf_counter_ns() - t0) / 1000.0)
                plan_idx = 0

        if not reached_all:
            break

    final_goal = q.goals[-1]
    reached = reached_all and pos == final_goal
    opt_ratio: float | None = None
    if reached:
        optimal_cost = _tour_cost(gt, q.goals, dist_from_start)
        if optimal_cost > 0 and optimal_cost < INF:
            opt_ratio = cost_walked / optimal_cost
        elif optimal_cost == 0:
            opt_ratio = 1.0
    elif dist_from_start[final_goal] >= INF:
        opt_ratio = None

    walk = Walk(
        final_pos=pos,
        cost_walked=cost_walked,
        steps_taken=steps,
        tiles_revealed=sum(sensor.seen),
        reached_all=reached_all,
        step_times_us=tuple(step_times),
    )
    return SpspResult(
        reached=reached,
        opt_ratio=opt_ratio,
        first_move_correct=first_move_correct,
        total_time_us=sum(step_times),
        walk=walk,
    )


def _empty_reading() -> SensorReading:
    return SensorReading(newly_visible=(), cost={})


def _tour_cost(gt: GroundTruth, goals: tuple[int, ...], first_dists: list[int]) -> int:
    if len(goals) == 1:
        return first_dists[goals[0]]
    total = first_dists[goals[0]]
    if total >= INF:
        return INF
    prev = goals[0]
    for g in goals[1:]:
        d = dijkstra_from(gt, prev)
        if d[g] >= INF:
            return INF
        total += d[g]
        prev = g
    return total


def run_sssp(
    algo: SsspAlgo,
    ctx: PrecompCtx,
    gt: GroundTruth,
    q: SsspQuery,
    cfg: RunCfg,
) -> SsspResult:
    ref = dijkstra_from(gt, q.start)
    t0 = time.perf_counter_ns()
    got = algo.solve(ctx, q.start)
    us = (time.perf_counter_ns() - t0) / 1000.0
    check = check_sssp(ref, got, algo.unit, cfg.hop_scale, ctx.n)
    return SsspResult(worst_ratio=check.worst_ratio, exact=check.exact, time_us=us)


def first_moves_for(
    gt: GroundTruth, start: int, goal: int, dist: list[int]
) -> set[int]:
    return optimal_first_moves(gt, start, goal, dist)
