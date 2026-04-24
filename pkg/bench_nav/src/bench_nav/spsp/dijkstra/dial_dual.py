from __future__ import annotations

from collections import deque
from typing import override

from bench_nav.common import CE, CR, INF, Path_, extract_dist
from bench_nav.precomputation import COST, PNB, PNB_DUAL
from bench_nav.types import (
    PrecompCtx,
    Spsp,
)

assert CR == 1
assert CE == 3


class DijkstraDialDual(Spsp):
    REQUIRES = frozenset({COST, PNB, PNB_DUAL})

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.n = ctx.n
        self.cost = ctx[COST]
        self.pnb = ctx[PNB]
        self.pnb1, self.pnb3 = ctx[PNB_DUAL]

    @override
    def plan(self, start: int, goal: int) -> Path_:
        cost = self.cost
        pnb = self.pnb
        pnb1 = self.pnb1
        pnb3 = self.pnb3
        dist = [INF] * self.n
        dist[start] = 0
        bk: list[deque[int]] = [deque() for _ in range(4)]
        bk[0].append(start)
        cur_d = 0
        emp = 0
        found = False
        while emp < 4:
            bki = bk[cur_d & 3]
            if bki:
                emp = 0
                popleft = bki.popleft
                nd1 = cur_d + 1
                bk1_append = bk[nd1 & 3].append
                nd3 = cur_d + 3
                bk3_append = bk[nd3 & 3].append
                while bki:
                    node = popleft()
                    if dist[node] != cur_d:
                        continue
                    if node == goal:
                        found = True
                        break
                    for nb in pnb1[node]:
                        if nd1 < dist[nb]:
                            dist[nb] = nd1
                            bk1_append(nb)
                    for nb in pnb3[node]:
                        if nd3 < dist[nb]:
                            dist[nb] = nd3
                            bk3_append(nb)
                if found:
                    break
            else:
                emp += 1
            cur_d += 1
        if not found:
            return None
        return extract_dist(dist, cost, pnb, start, goal)
