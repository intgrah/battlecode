from __future__ import annotations

from typing import override

from bench_nav.common import INF
from bench_nav.sssp.bfs._base import BfsBase


class BfsSkipUnrolled(BfsBase):
    SKIP = True

    @override
    def solve(self, start: int) -> list[int]:
        inf = INF
        pnb_push = self.pnb_push
        pnb_set = self.pnb_set
        dist = [inf] * self.n
        dist[start] = 0
        a: list[int] = [start]
        b: list[int] = []
        a_append = a.append
        b_append = b.append
        d = 1
        while a:
            for node in a:
                for nb in pnb_push[node]:
                    if dist[nb] is inf:
                        dist[nb] = d
                        b_append(nb)
                for nb in pnb_set[node]:
                    if dist[nb] is inf:
                        dist[nb] = d
            a.clear()
            d += 1
            for node in b:
                for nb in pnb_push[node]:
                    if dist[nb] is inf:
                        dist[nb] = d
                        a_append(nb)
                for nb in pnb_set[node]:
                    if dist[nb] is inf:
                        dist[nb] = d
            b.clear()
            d += 1
        return dist
