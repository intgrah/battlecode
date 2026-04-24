from __future__ import annotations

from typing import override

from bench_nav.common import INF
from bench_nav.sssp.bfs.jps._base import JpsDirBase


class BfsJpsListDbl(JpsDirBase):
    @override
    def solve(self, start: int) -> list[int]:
        pnb_dir = self.pnb_dir
        dir_of_offset = self.dir_of_offset
        dist = [INF] * self.n
        dist[start] = 0
        pnb_at: list[list[int]] = [pnb_dir[0][8]] * self.n
        pnb_at[start] = pnb_dir[start][8]
        a: list[int] = [start]
        b: list[int] = []
        a_append = a.append
        b_append = b.append
        d = 1
        while a:
            for node in a:
                for nb in pnb_at[node]:
                    if dist[nb] is INF:
                        dist[nb] = d
                        pnb_at[nb] = pnb_dir[nb][dir_of_offset[nb - node]]
                        b_append(nb)
            a.clear()
            d += 1
            for node in b:
                for nb in pnb_at[node]:
                    if dist[nb] is INF:
                        dist[nb] = d
                        pnb_at[nb] = pnb_dir[nb][dir_of_offset[nb - node]]
                        a_append(nb)
            b.clear()
            d += 1
        return dist
