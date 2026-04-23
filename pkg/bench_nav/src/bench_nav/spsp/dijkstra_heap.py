from __future__ import annotations

import heapq
from typing import Final

from bench_nav.common import INF, Path_, extract_parent
from bench_nav.precompute import COST, PNB
from bench_nav.types import (
    AlgoName,
    PrecompCtx,
    SensorReading,
    SequentialSpspAlgo,
)


def _dijkstra_heap(
    n: int,
    cost: list[int],
    pnb: list[list[int]],
    start: int,
    goal: int,
) -> Path_:
    dist = [INF] * n
    dist[start] = 0
    parent = [-1] * n
    parent[start] = start
    q = [(0, start)]
    while q:
        d, node = heapq.heappop(q)
        if node == goal:
            return extract_parent(parent, start, goal)
        if d > dist[node]:
            continue
        g_node = dist[node]
        for nb in pnb[node]:
            c = cost[nb]
            nd = g_node + c
            if nd < dist[nb]:
                dist[nb] = nd
                parent[nb] = node
                heapq.heappush(q, (nd, nb))
    return None


def _init(
    ctx: PrecompCtx, _r: SensorReading, start: int, goal: int
) -> tuple[PrecompCtx, Path_]:
    return ctx, _dijkstra_heap(ctx.n, ctx[COST], ctx[PNB], start, goal)


def _step(
    ctx: PrecompCtx, _r: SensorReading, pos: int, goal: int
) -> tuple[PrecompCtx, Path_]:
    return ctx, _dijkstra_heap(ctx.n, ctx[COST], ctx[PNB], pos, goal)


ALGO: Final[SequentialSpspAlgo[PrecompCtx]] = SequentialSpspAlgo(
    name=AlgoName("dijkstra-heap"),
    requires=frozenset({COST, PNB}),
    init=_init,
    step=_step,
)
