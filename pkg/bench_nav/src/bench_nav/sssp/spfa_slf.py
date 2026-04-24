from __future__ import annotations

from collections import deque
from typing import override

from bench_nav.common import CR, INF
from bench_nav.precomputation import COST, PNB
from bench_nav.types import CostUnit, PrecompCtx, Sssp

assert CR == 1


class SpfaSlf(Sssp):
    REQUIRES = frozenset({COST, PNB})
    UNIT = CostUnit.COST

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.n = ctx.n
        self.cost = ctx[COST]
        self.pnb = ctx[PNB]

    @override
    def solve(self, start: int) -> list[int]:
        cost = self.cost
        pnb = self.pnb
        dist = [INF] * self.n
        dist[start] = 0
        q = deque([start])
        popleft = q.popleft
        appendleft = q.appendleft
        append = q.append
        while q:
            node = popleft()
            d = dist[node]
            for nb in pnb[node]:
                nd = d + cost[nb]
                if nd < dist[nb]:
                    dist[nb] = nd
                    if cost[nb] == 1:
                        appendleft(nb)
                    else:
                        append(nb)
        return dist
