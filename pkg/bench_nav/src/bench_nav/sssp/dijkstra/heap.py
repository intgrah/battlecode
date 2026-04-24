from __future__ import annotations

import heapq
from typing import override

from bench_nav.common import INF
from bench_nav.sssp.dijkstra._base import DijkstraBase


class DijkstraHeapSssp(DijkstraBase):
    @override
    def solve(self, start: int) -> list[int]:
        n = self.n
        cost = self.cost
        pnb = self.pnb
        dist = [INF] * n
        dist[start] = 0
        q = [(0, start)]
        while q:
            d, node = heapq.heappop(q)
            if d > dist[node]:
                continue
            for nb in pnb[node]:
                nd = d + cost[nb]
                if nd < dist[nb]:
                    dist[nb] = nd
                    heapq.heappush(q, (nd, nb))
        return dist
