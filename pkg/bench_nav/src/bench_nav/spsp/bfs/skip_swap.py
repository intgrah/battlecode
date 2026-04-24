from __future__ import annotations

from typing import override

from bench_nav.common import INF, Path_
from bench_nav.spsp.bfs._base import BfsSkipBase


class BfsSkipSwap(BfsSkipBase):
    @override
    def plan(self, start: int, goal: int) -> Path_:
        inf = INF
        cost = self.cost
        pnb = self.pnb
        pnb_push = self.pnb_push
        pnb_set = self.pnb_set
        dist = [inf] * self.n
        dist[start] = 0
        frontier: list[int] = [start]
        next_frontier: list[int] = []
        d = 1
        while frontier:
            append = next_frontier.append
            for node in frontier:
                for nb in pnb_push[node]:
                    if dist[nb] is inf:
                        dist[nb] = d
                        append(nb)
                for nb in pnb_set[node]:
                    if dist[nb] is inf:
                        dist[nb] = d
            if dist[goal] is not inf:
                break
            frontier, next_frontier = next_frontier, frontier
            next_frontier.clear()
            d += 1
        if dist[goal] is inf:
            return None
        path = [goal]
        cur = goal
        while cur != start:
            d = dist[cur]
            best = -1
            best_cost = inf + 1
            for nb in pnb[cur]:
                if dist[nb] == d - 1 and cost[nb] < best_cost:
                    best = nb
                    best_cost = cost[nb]
            if best == -1:
                return None
            path.append(best)
            cur = best
        path.reverse()
        return path
