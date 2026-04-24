from __future__ import annotations

from collections import deque
from typing import override

from bench_nav.common import CE, INF
from bench_nav.precomputation import PNBC_NAVDIJKSTRA
from bench_nav.types import CostUnit, PrecompCtx, Sssp

assert CE + 1 == 4


class DijkstraDialSkipPnbc(Sssp):
    REQUIRES = frozenset({PNBC_NAVDIJKSTRA})
    UNIT = CostUnit.COST

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.n = ctx.n
        self.pnb_push_c, self.pnb_set_c = ctx[PNBC_NAVDIJKSTRA]

    @override
    def solve(self, start: int) -> list[int]:
        pnb_push_c = self.pnb_push_c
        pnb_set_c = self.pnb_set_c
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
                    for nb, c in pnb_push_c[node]:
                        nd = cur_d + c
                        if nd < dist[nb]:
                            dist[nb] = nd
                            bk[nd & 0b11].append(nb)
                    for nb, c in pnb_set_c[node]:
                        nd = cur_d + c
                        dist[nb] = min(dist[nb], nd)
            else:
                emp += 1
            cur_d += 1
        return dist
