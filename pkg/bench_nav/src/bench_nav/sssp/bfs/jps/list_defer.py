from __future__ import annotations

from typing import override

from bench_nav.common import INF
from bench_nav.sssp.bfs.jps._base import JpsOffsetBase


class BfsJpsListDefer(JpsOffsetBase):
    @override
    def solve(self, start: int) -> list[int]:
        pnb_by_offset = self.pnb_by_offset
        sentinel: list[int] = []
        pnb_at = [sentinel] * self.n
        pnb_at[start] = pnb_by_offset[start][0]
        frontier = [start]
        levels = [frontier]
        while frontier:
            next_frontier: list[int] = []
            for node in frontier:
                for nb in pnb_at[node]:
                    if pnb_at[nb] is sentinel:
                        pnb_at[nb] = pnb_by_offset[nb][nb - node]
                        next_frontier.append(nb)
            levels.append(next_frontier)
            frontier = next_frontier
        dist = [INF] * self.n
        for d, level in enumerate(levels):
            for nb in level:
                dist[nb] = d
        return dist
