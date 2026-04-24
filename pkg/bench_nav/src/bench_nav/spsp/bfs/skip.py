from __future__ import annotations

from typing import override

from bench_nav.common import INF, Path_
from bench_nav.spsp.bfs._base import BfsSkipBase


class BfsSkip(BfsSkipBase):
    @override
    def plan(self, start: int, goal: int) -> Path_:
        cost = self.cost
        pnb = self.pnb
        pnb_push = self.pnb_push
        pnb_set = self.pnb_set
        dist = [INF] * self.n
        dist[start] = 0
        q = [start]
        append = q.append
        stop_at = INF
        for node in q:
            d = dist[node] + 1
            if node == goal:
                stop_at = d
            if d > stop_at:
                break
            for nb in pnb_push[node]:
                if d < dist[nb]:
                    dist[nb] = d
                    append(nb)
            for nb in pnb_set[node]:
                if d < dist[nb]:
                    if nb == goal:
                        stop_at = d + 1
                    dist[nb] = d
        if dist[goal] >= INF:
            return None
        path = [goal]
        cur = goal
        while cur != start:
            d = dist[cur]
            best = -1
            best_cost = INF + 1
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
