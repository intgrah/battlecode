from __future__ import annotations

import heapq
from typing import override

from bench_nav.common import INF, Path_, extract_parent
from bench_nav.spsp.astar._base import AstarApspBase


class AstarHeapApsp(AstarApspBase):
    @override
    def plan(self, start: int, goal: int) -> Path_:
        cost = self.cost
        pnb = self.pnb
        h_to_goal = self.apsp_cols[goal]
        g = [INF] * self.n
        g[start] = 0
        parent = [-1] * self.n
        parent[start] = start
        h_start = h_to_goal[start]
        q = [(h_start, h_start, start)]
        while q:
            f, h_node, node = heapq.heappop(q)
            if f > g[node] + h_node:
                continue
            if node == goal:
                return extract_parent(parent, start, goal)
            g_node = g[node]
            for nb in pnb[node]:
                nd = g_node + cost[nb]
                if nd < g[nb]:
                    g[nb] = nd
                    parent[nb] = node
                    h_nb = h_to_goal[nb]
                    heapq.heappush(q, (nd + h_nb, h_nb, nb))
        return None
