from __future__ import annotations

from typing import override

from bench_nav.common import INF
from bench_nav.sssp.bfs._base import BfsBase


class BfsAlloc(BfsBase):
    @override
    def solve(self, start: int) -> list[int]:
        pnb = self.pnb
        dist = [INF] * self.n
        dist[start] = 0
        frontier = [start]
        d = 1
        while frontier:
            next_frontier: list[int] = []
            for node in frontier:
                for nb in pnb[node]:
                    if dist[nb] is INF:
                        dist[nb] = d
                        next_frontier.append(nb)
            frontier = next_frontier
            d += 1
        return dist
