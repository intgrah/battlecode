from __future__ import annotations

from typing import override

from bench_nav.common import INF
from bench_nav.precomputation import COST, PNB
from bench_nav.types import CostUnit, PrecompCtx, Sssp


class BellmanFord(Sssp):
    REQUIRES = frozenset({COST, PNB})
    UNIT = CostUnit.COST

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.n = ctx.n
        self.cost = ctx[COST]
        self.pnb = ctx[PNB]

    @override
    def solve(self, start: int) -> list[int]:
        n = self.n
        cost = self.cost
        pnb = self.pnb
        dist = [INF] * n
        dist[start] = 0
        for _ in range(n - 1):
            changed = False
            for node in range(n):
                d = dist[node]
                if d is not INF:
                    for nb in pnb[node]:
                        nd = d + cost[nb]
                        if nd < dist[nb]:
                            dist[nb] = nd
                            changed = True
            if not changed:
                break
        return dist
