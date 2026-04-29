from __future__ import annotations

import heapq
from typing import TYPE_CHECKING, override

from bench_nav.common import INF, Path_, bfs_dist, extract_parent
from bench_nav.spsp.astar._base import AstarBase

if TYPE_CHECKING:
    from bench_nav.types import PrecompCtx


class AstarHeapBfs(AstarBase):
    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        super().__init__(ctx)
        self._h_cache: dict[int, list[int]] = {}

    @override
    def plan(self, start: int, goal: int) -> Path_:
        cost = self.cost
        pnb = self.pnb
        h_to_goal = self._h_cache.get(goal)
        if h_to_goal is None:
            h_to_goal = bfs_dist(self.n, pnb, goal)
            self._h_cache[goal] = h_to_goal
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
