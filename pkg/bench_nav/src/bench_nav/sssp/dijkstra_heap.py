from __future__ import annotations

import heapq
from typing import Final

from bench_nav.common import INF
from bench_nav.precompute import COST, PNB
from bench_nav.types import AlgoName, CostUnit, PrecompCtx, SsspAlgo


def _solve(ctx: PrecompCtx, start: int) -> list[int]:
    n = ctx.n
    cost = ctx[COST]
    pnb = ctx[PNB]
    dist = [INF] * n
    dist[start] = 0
    q = [(0, start)]
    while q:
        d, node = heapq.heappop(q)
        if d > dist[node]:
            continue
        for nb in pnb[node]:
            nd = d + cost[nb]
            if nd < dist[nb]:
                dist[nb] = nd
                heapq.heappush(q, (nd, nb))
    return dist


ALGO: Final[SsspAlgo] = SsspAlgo(
    name=AlgoName("dijkstra-heap"),
    requires=frozenset({COST, PNB}),
    unit=CostUnit.COST,
    solve=_solve,
)
