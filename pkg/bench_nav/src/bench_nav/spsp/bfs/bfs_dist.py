from __future__ import annotations

from typing import override

from bench_nav.common import CE, INF, Path_
from bench_nav.precomputation import PNB
from bench_nav.types import (
    PrecompCtx,
    Spsp,
)

assert CE == 3


class BfsDist(Spsp):
    REQUIRES = frozenset({PNB})

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.n = ctx.n
        self.pnb = ctx[PNB]

    @override
    def plan(self, start: int, goal: int) -> Path_:
        pnb = self.pnb
        dist = [INF] * self.n
        dist[start] = 0
        q = [start]
        append = q.append
        for node in q:
            d = dist[node] + 1
            for nb in pnb[node]:
                if d < dist[nb]:
                    dist[nb] = d
                    append(nb)
        if dist[goal] >= INF:
            return None
        path = [goal]
        cur = goal
        while cur != start:
            d = dist[cur] - 1
            for nb in pnb[cur]:
                if dist[nb] == d:
                    path.append(nb)
                    cur = nb
                    break
            else:
                return None
        path.reverse()
        return path
