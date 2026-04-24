from __future__ import annotations

from typing import override

from bench_nav.common import INF
from bench_nav.sssp.bfs._base import BfsBase


class BfsSkipSwap(BfsBase):
    SKIP = True

    @override
    def solve(self, start: int) -> list[int]:
        inf = INF
        pnb_push = self.pnb_push
        pnb_set = self.pnb_set
        dist = [inf] * self.n
        dist[start] = 0
        frontier: list[int] = [start]
        next_frontier: list[int] = []
        d = 1
        while frontier:
            append = next_frontier.append
            for node in frontier:
                for nb in pnb_push[node]:
                    if dist[nb] is inf:
                        dist[nb] = d
                        append(nb)
                for nb in pnb_set[node]:
                    if dist[nb] is inf:
                        dist[nb] = d
            frontier, next_frontier = next_frontier, frontier
            next_frontier.clear()
            d += 1
        return dist
