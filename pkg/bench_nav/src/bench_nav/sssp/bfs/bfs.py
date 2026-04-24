from __future__ import annotations

from typing import override

from bench_nav.common import INF
from bench_nav.sssp.bfs._base import BfsBase


class Bfs(BfsBase):
    @override
    def solve(self, start: int) -> list[int]:
        pnb = self.pnb
        dist = [INF] * self.n
        dist[start] = 0
        q = [start]
        append = q.append
        for node in q:
            d1 = dist[node] + 1
            for nb in pnb[node]:
                if dist[nb] is INF:
                    dist[nb] = d1
                    append(nb)
        return dist
