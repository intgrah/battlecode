from __future__ import annotations

from typing import override

from bench_nav.common import INF
from bench_nav.precomputation import PNB
from bench_nav.types import CostUnit, PrecompCtx, Sssp

_MAX_D = 300


class BfsBuckets(Sssp):
    REQUIRES = frozenset({PNB})
    UNIT = CostUnit.HOPS

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.n = ctx.n
        self.pnb = ctx[PNB]

    @override
    def solve(self, start: int) -> list[int]:
        pnb = self.pnb
        dist = [INF] * self.n
        dist[start] = 0
        buckets: list[list[int]] = [[] for _ in range(_MAX_D)]
        buckets[0].append(start)
        d = 1
        for frontier in buckets:
            if not frontier:
                break
            append = buckets[d].append
            for node in frontier:
                for nb in pnb[node]:
                    if dist[nb] is INF:
                        dist[nb] = d
                        append(nb)
            d += 1
        return dist
