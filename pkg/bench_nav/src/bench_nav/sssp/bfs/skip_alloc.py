from __future__ import annotations

from typing import override

from bench_nav.common import INF
from bench_nav.sssp.bfs._base import BfsBase


class BfsSkipAlloc(BfsBase):
    SKIP = True

    @override
    def solve(self, start: int) -> list[int]:
        inf = INF
        pnb_push = self.pnb_push
        pnb_set = self.pnb_set
        dist = [inf] * self.n
        dist[start] = 0
        frontier = [start]
        d = 1
        while frontier:
            next_frontier: list[int] = []
            for node in frontier:
                for nb in pnb_push[node]:
                    if dist[nb] is inf:
                        dist[nb] = d
                        next_frontier.append(nb)
                for nb in pnb_set[node]:
                    if dist[nb] is inf:
                        dist[nb] = d
            frontier = next_frontier
            d += 1
        return dist
