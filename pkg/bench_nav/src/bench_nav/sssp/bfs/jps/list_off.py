from __future__ import annotations

from typing import override

from bench_nav.common import INF
from bench_nav.sssp.bfs.jps._base import JpsOffsetBase


class BfsJpsListOff(JpsOffsetBase):
    @override
    def solve(self, start: int) -> list[int]:
        pnb_by_offset = self.pnb_by_offset
        sentinel: list[int] = []
        dist = [INF] * self.n
        dist[start] = 0
        pnb = [sentinel] * self.n
        pnb[start] = pnb_by_offset[start][0]
        frontier = [start]
        d = 1
        while frontier:
            next_frontier: list[int] = []
            for node in frontier:
                for nb in pnb[node]:
                    if dist[nb] is INF:
                        dist[nb] = d
                        pnb[nb] = pnb_by_offset[nb][nb - node]
                        next_frontier.append(nb)
            frontier = next_frontier
            d += 1
        return dist
