from __future__ import annotations

from typing import Final, override

from bench_nav.common import INF
from bench_nav.sssp.bfs._base import BfsBase


class BfsSkip(BfsBase):
    SKIP = True

    @override
    def solve(self, start: int) -> list[int]:
        inf: Final = INF
        pnb_push = self.pnb_push
        pnb_set = self.pnb_set
        dist = [inf] * self.n
        dist[start] = 0
        q = [start]
        append = q.append
        for node in q:
            d = dist[node] + 1
            for nb in pnb_push[node]:
                if dist[nb] is inf:
                    dist[nb] = d
                    append(nb)
            for nb in pnb_set[node]:
                if dist[nb] is inf:
                    dist[nb] = d
        return dist
