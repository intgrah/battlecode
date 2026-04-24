from __future__ import annotations

from collections import deque
from typing import override

from bench_nav.common import INF
from bench_nav.sssp.dijkstra._base import DijkstraBase


class DijkstraDialUnrolled(DijkstraBase):
    @override
    def solve(self, start: int) -> list[int]:
        cost = self.cost
        pnb = self.pnb
        dist = [INF] * self.n
        dist[start] = 0
        bk0: deque[int] = deque()
        bk1: deque[int] = deque()
        bk2: deque[int] = deque()
        bk3: deque[int] = deque()
        bk = (bk0, bk1, bk2, bk3)
        bk0.append(start)
        cur_d = 0
        while bk0 or bk1 or bk2 or bk3:
            bki = bk[cur_d & 0b11]
            if bki:
                popleft = bki.popleft
                while bki:
                    node = popleft()
                    if dist[node] != cur_d:
                        continue
                    for nb in pnb[node]:
                        nd = cur_d + cost[nb]
                        if nd < dist[nb]:
                            dist[nb] = nd
                            bk[nd & 0b11].append(nb)
            cur_d += 1
        return dist
