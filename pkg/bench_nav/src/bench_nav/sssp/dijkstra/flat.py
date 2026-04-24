from __future__ import annotations

from typing import override

from bench_nav.common import INF
from bench_nav.sssp.dijkstra._base import DijkstraBase

_BUCKETS = 900


class DijkstraFlat(DijkstraBase):
    @override
    def solve(self, start: int) -> list[int]:
        cost = self.cost
        pnb = self.pnb
        dist = [INF] * self.n
        dist[start] = 0
        bk: list[list[int]] = [[] for _ in range(_BUCKETS)]
        bk[0].append(start)
        cur_d = 0
        max_d = 0
        while cur_d <= max_d:
            for node in bk[cur_d]:
                if dist[node] == cur_d:
                    for nb in pnb[node]:
                        nd = cur_d + cost[nb]
                        if nd < dist[nb]:
                            dist[nb] = nd
                            bk[nd].append(nb)
                            if nd > max_d:  # noqa: PLR1730
                                max_d = nd
            cur_d += 1
        return dist
