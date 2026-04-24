from __future__ import annotations

import heapq
from typing import override

from bench_nav.common import CR, INF, Path_, extract_parent
from bench_nav.precomputation import PNB
from bench_nav.types import (
    PrecompCtx,
    Spsp,
)


class Gbfs(Spsp):
    REQUIRES = frozenset({PNB})

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.w = ctx.w
        self.n = ctx.n
        self.pnb = ctx[PNB]

    @override
    def plan(self, start: int, goal: int) -> Path_:
        w = self.w
        pnb = self.pnb
        start_x, start_y = start % w, start // w
        goal_x, goal_y = goal % w, goal // w
        parent = [-1] * self.n
        parent[start] = start
        h_start = max(abs(start_x - goal_x), abs(start_y - goal_y)) * CR
        q = [(h_start, start)]
        best_h = INF
        best_node = start
        while q:
            h_node, node = heapq.heappop(q)
            if node == goal:
                return extract_parent(parent, start, goal)
            if h_node < best_h:
                best_h = h_node
                best_node = node
            for nb in pnb[node]:
                if parent[nb] != -1:
                    continue
                parent[nb] = node
                h_nb = max(abs(nb % w - goal_x), abs(nb // w - goal_y)) * CR
                heapq.heappush(q, (h_nb, nb))
        if best_node == start:
            return None
        return extract_parent(parent, start, best_node)
