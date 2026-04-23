from __future__ import annotations

from typing import Final

from bench_nav.common import INF
from bench_nav.precompute import PNB
from bench_nav.types import AlgoName, CostUnit, PrecompCtx, SsspAlgo


def _solve(ctx: PrecompCtx, start: int) -> list[int]:
    n = ctx.n
    pnb = ctx[PNB]
    dist = [INF] * n
    dist[start] = 0
    q = [start]
    append = q.append
    for node in q:
        d1 = dist[node] + 1
        for nb in pnb[node]:
            if dist[nb] is INF:
                dist[nb] = d1
                append(nb)
    return dist


ALGO: Final[SsspAlgo] = SsspAlgo(
    name=AlgoName("bfs"),
    requires=frozenset({PNB}),
    unit=CostUnit.HOPS,
    solve=_solve,
)
