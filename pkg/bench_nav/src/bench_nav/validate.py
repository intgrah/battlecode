from __future__ import annotations

import heapq
import sys
from dataclasses import dataclass

from bench_nav.common import INF, Path_
from bench_nav.types import CostUnit


@dataclass(frozen=True)
class GroundTruth:
    w: int
    n: int
    cost: list[int]
    pnb: list[list[int]]


def dijkstra_from(gt: GroundTruth, start: int) -> list[int]:
    dist: list[int] = [INF] * gt.n
    dist[start] = 0
    heap: list[tuple[int, int]] = [(0, start)]
    while heap:
        d, node = heapq.heappop(heap)
        if d > dist[node]:
            continue
        for nb in gt.pnb[node]:
            nd = d + gt.cost[nb]
            if nd < dist[nb]:
                dist[nb] = nd
                heapq.heappush(heap, (nd, nb))
    return dist


def optimal_first_moves(
    gt: GroundTruth, start: int, goal: int, dist: list[int]
) -> set[int]:
    if start == goal:
        return {start}
    if dist[goal] >= INF:
        return set()
    on_shortest: list[bool] = [False] * gt.n
    on_shortest[goal] = True
    q = [goal]
    for node in q:
        for nb in gt.pnb[node]:
            if on_shortest[nb]:
                continue
            if dist[nb] + gt.cost[node] == dist[node]:
                on_shortest[nb] = True
                q.append(nb)
    moves: set[int] = set()
    for nb in gt.pnb[start]:
        if on_shortest[nb] and dist[start] + gt.cost[nb] == dist[nb]:
            moves.add(nb)
    return moves


def path_cost(gt: GroundTruth, path: list[int]) -> int:
    if len(path) < 2:
        return 0
    total = 0
    for k in range(len(path) - 1):
        a, b = path[k], path[k + 1]
        ax, ay = a % gt.w, a // gt.w
        bx, by = b % gt.w, b // gt.w
        if abs(bx - ax) > 1 or abs(by - ay) > 1:
            return INF
        c = gt.cost[b]
        if c >= INF:
            return INF
        total += c
    return total


def validate_path(
    gt: GroundTruth, path: list[int], start: int, algo_name: str, map_name: str
) -> bool:
    if not path:
        return True
    if path[0] != start:
        print(
            f"INVALID {algo_name} on {map_name}: start={path[0]} expected={start}",
            file=sys.stderr,
        )
        return False
    for k, node in enumerate(path):
        if node < 0 or node >= gt.n:
            print(
                f"INVALID {algo_name} on {map_name}: node {k} out of bounds: {node}",
                file=sys.stderr,
            )
            return False
        if k > 0 and gt.cost[node] >= INF:
            print(
                f"INVALID {algo_name} on {map_name}: node {k} impassable: {node}",
                file=sys.stderr,
            )
            return False
    for k in range(len(path) - 1):
        a, b = path[k], path[k + 1]
        if abs(a % gt.w - b % gt.w) > 1 or abs(a // gt.w - b // gt.w) > 1:
            print(
                f"INVALID {algo_name} on {map_name}: non-adjacent step {k}",
                file=sys.stderr,
            )
            return False
    return True


@dataclass(frozen=True)
class SpspQueryCheck:
    reached: bool
    opt_ratio: float | None
    first_move_correct: bool | None


def check_spsp(
    gt: GroundTruth,
    dist_from_start: list[int],
    first_moves: set[int],
    path: Path_,
    start: int,
    goal: int,
) -> SpspQueryCheck:
    gd = dist_from_start[goal]
    if gd >= INF:
        return SpspQueryCheck(reached=False, opt_ratio=None, first_move_correct=None)
    if start == goal:
        return SpspQueryCheck(reached=True, opt_ratio=1.0, first_move_correct=True)
    if path is None or len(path) < 1:
        return SpspQueryCheck(reached=False, opt_ratio=None, first_move_correct=None)
    pc = path_cost(gt, path)
    reached = path[-1] == goal and pc < INF
    ratio = pc / gd if reached and gd > 0 else None
    fm: bool | None = None
    if len(path) >= 2:
        fm = path[1] in first_moves
    return SpspQueryCheck(reached=reached, opt_ratio=ratio, first_move_correct=fm)


@dataclass(frozen=True)
class SsspQueryCheck:
    worst_ratio: float
    exact: bool


def check_sssp(
    ref: list[int],
    got: list[int],
    unit: CostUnit,
    hop_scale: int,
    n: int,
) -> SsspQueryCheck:
    scaled: list[int]
    if unit is CostUnit.HOPS:
        scaled = [d * hop_scale if d < INF else INF for d in got]
    else:
        scaled = got
    exact = all(scaled[i] == ref[i] for i in range(n))
    worst = 1.0
    for i in range(n):
        if ref[i] < INF and ref[i] > 0 and scaled[i] < INF:
            r = scaled[i] / ref[i]
            worst = max(worst, r)
    return SsspQueryCheck(worst_ratio=worst, exact=exact)
