from __future__ import annotations

from collections import deque
from typing import override

from bench_nav.common import CE, INF
from bench_nav.precomputation import COST, PNB_NAVDIJKSTRA
from bench_nav.types import CostUnit, PrecompCtx, Sssp

assert CE + 1 == 4


class DijkstraDialSkip(Sssp):
    REQUIRES = frozenset({COST, PNB_NAVDIJKSTRA})
    UNIT = CostUnit.COST

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.n = ctx.n
        self.cost = ctx[COST]
        self.pnb_push, self.pnb_set = ctx[PNB_NAVDIJKSTRA]

    @override
    def solve(self, start: int) -> list[int]:
        cost = self.cost
        pnb_push = self.pnb_push
        pnb_set = self.pnb_set
        dist = [INF] * self.n
        dist[start] = 0
        bk: list[deque[int]] = [deque() for _ in range(4)]
        bk[0].append(start)
        cur_d = 0
        emp = 0
        while emp < 4:
            bki = bk[cur_d & 0b11]
            if bki:
                emp = 0
                popleft = bki.popleft
                while bki:
                    node = popleft()
                    if dist[node] != cur_d:
                        continue
                    for nb in pnb_push[node]:
                        nd = cur_d + cost[nb]
                        if nd < dist[nb]:
                            dist[nb] = nd
                            bk[nd & 0b11].append(nb)
                    for nb in pnb_set[node]:
                        nd = cur_d + cost[nb]
                        dist[nb] = min(dist[nb], nd)
            else:
                emp += 1
            cur_d += 1
        return dist
