from __future__ import annotations

from collections import deque
from typing import override

from bench_nav.common import INF
from bench_nav.precomputation import COST, PNB
from bench_nav.types import CostUnit, PrecompCtx, Sssp


class BfsExpand(Sssp):
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
        n2 = n + n
        dist = [INF] * (n + n2)
        dist[start] = 0
        q = deque([start])
        popleft = q.popleft
        append = q.append
        while q:
            node = popleft()
            d1 = dist[node] + 1
            if node < n:
                for nb in pnb[node]:
                    c = cost[nb]
                    if c == 1:
                        if dist[nb] is INF:
                            dist[nb] = d1
                            append(nb)
                    else:
                        vi = nb + n2
                        if dist[vi] is INF:
                            dist[vi] = d1
                            append(vi)
            elif node >= n2:
                nb = node - n
                if dist[nb] is INF:
                    dist[nb] = d1
                    append(nb)
            else:
                nb = node - n
                if dist[nb] is INF:
                    dist[nb] = d1
                    append(nb)
        result = [INF] * n
        result[start] = 0
        for i in range(n):
            if dist[i] is not INF:
                result[i] = dist[i]
        return result
