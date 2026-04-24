from __future__ import annotations

from typing import override

from bench_nav.common import INF
from bench_nav.sssp.bfs.jps._base import JpsDirBase


class BfsJpsListMerge(JpsDirBase):
    @override
    def solve(self, start: int) -> list[int]:
        pnb_dir = self.pnb_dir
        dir_of_offset = self.dir_of_offset
        sentinel: list[int] = []
        pnb_at: list[list[int]] = [sentinel] * self.n
        pnb_at[start] = pnb_dir[start][8]
        dist = [INF] * self.n
        dist[start] = 0
        frontier: list[int] = [start]
        d = 1
        while frontier:
            next_frontier: list[int] = []
            for node in frontier:
                for nb in pnb_at[node]:
                    if pnb_at[nb] is sentinel:
                        pnb_at[nb] = pnb_dir[nb][dir_of_offset[nb - node]]
                        next_frontier.append(nb)
            for nb in next_frontier:
                dist[nb] = d
            frontier = next_frontier
            d += 1
        return dist
