from __future__ import annotations

from typing import override

from bench_nav.common import INF
from bench_nav.sssp.bfs.jps._base import JpsDirBase


class BfsJps(JpsDirBase):
    @override
    def solve(self, start: int) -> list[int]:
        pnb_dir = self.pnb_dir
        dir_of_offset = self.dir_of_offset
        dist = [INF] * self.n
        dist[start] = 0
        entry_dir_at = [8] * self.n
        frontier: list[int] = [start]
        d = 1
        while frontier:
            next_frontier: list[int] = []
            for node in frontier:
                for nb in pnb_dir[node][entry_dir_at[node]]:
                    if dist[nb] is INF:
                        dist[nb] = d
                        entry_dir_at[nb] = dir_of_offset[nb - node]
                        next_frontier.append(nb)
            frontier = next_frontier
            d += 1
        return dist
