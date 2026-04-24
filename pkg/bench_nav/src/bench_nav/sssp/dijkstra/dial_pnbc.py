from __future__ import annotations

from collections import deque
from typing import override

from bench_nav.common import INF
from bench_nav.precomputation import PNBC
from bench_nav.types import CostUnit, PrecompCtx, Sssp


class DijkstraDialPnbc(Sssp):
    REQUIRES = frozenset({PNBC})
    UNIT = CostUnit.COST

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.n = ctx.n
        self.pnbc = ctx[PNBC]

    @override
    def solve(self, start: int) -> list[int]:
        pnbc = self.pnbc
        dist = [INF] * self.n
        dist[start] = 0
        bk: list[deque[int]] = [deque() for _ in range(4)]
        bk[0].append(start)
        cur_d = 0
        emp = 0
        while emp < 4:
            bi = cur_d & 3
            bki = bk[bi]
            if not bki:
                cur_d += 1
                emp += 1
                continue
            emp = 0
            node = bki.popleft()
            if dist[node] != cur_d:
                continue
            for nb, c in pnbc[node]:
                nd = cur_d + c
                if nd < dist[nb]:
                    dist[nb] = nd
                    bk[nd & 3].append(nb)
        return dist
