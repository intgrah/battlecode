from __future__ import annotations

from collections import deque
from typing import override

from bench_nav.common import CE, CR, INF
from bench_nav.precomputation import PNB_DUAL
from bench_nav.types import CostUnit, PrecompCtx, Sssp


class DijkstraDialNpDual2(Sssp):
    REQUIRES = frozenset({PNB_DUAL})
    UNIT = CostUnit.COST

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.n = ctx.n
        self.pnb1, self.pnb3 = ctx[PNB_DUAL]

    @override
    def solve(self, start: int) -> list[int]:
        cr, ce = CR, CE
        pnb1 = self.pnb1
        pnb3 = self.pnb3
        dist = [INF] * self.n
        dist[start] = 0
        bk: list[deque[int]] = [deque() for _ in range(4)]
        bk[0].append(start)
        cur_d = 0
        emp = 0
        while emp < 4:
            bki = bk[cur_d & 3]
            if not bki:
                cur_d += 1
                emp += 1
                continue
            emp = 0
            node = bki.popleft()
            if dist[node] != cur_d:
                continue
            nd1 = cur_d + cr
            bk1_append = bk[nd1 & 3].append
            for nb in pnb1[node]:
                if nd1 < dist[nb]:
                    dist[nb] = nd1
                    bk1_append(nb)
            nd3 = cur_d + ce
            bk3_append = bk[nd3 & 3].append
            for nb in pnb3[node]:
                if nd3 < dist[nb]:
                    dist[nb] = nd3
                    bk3_append(nb)
        return dist
