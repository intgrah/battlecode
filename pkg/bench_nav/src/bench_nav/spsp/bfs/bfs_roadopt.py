from __future__ import annotations

from typing import override

from bench_nav.common import Path_, extract_parent
from bench_nav.precomputation import COST, PNB
from bench_nav.types import (
    PrecompCtx,
    Spsp,
)


class BfsRoadopt(Spsp):
    REQUIRES = frozenset({COST, PNB})

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.n = ctx.n
        self.cost = ctx[COST]
        self.pnb = ctx[PNB]

    @override
    def plan(self, start: int, goal: int) -> Path_:
        cost = self.cost
        pnb = self.pnb
        parent = [-1] * self.n
        parent[start] = start
        q = [start]
        append = q.append
        found = False
        for node in q:
            for nb in pnb[node]:
                if parent[nb] != -1:
                    continue
                parent[nb] = node
                if nb == goal:
                    found = True
                    break
                append(nb)
            if found:
                break
        if not found:
            return None
        path = extract_parent(parent, start, goal)
        if path is None or len(path) < 3:
            return path
        next_next = path[2]
        best_nb = path[1]
        best_cost = cost[best_nb]
        for nb in pnb[start]:
            if cost[nb] >= best_cost or parent[nb] != start:
                continue
            adjacent_to_next = False
            for nb2 in pnb[nb]:
                if nb2 == next_next:
                    adjacent_to_next = True
                    break
            if adjacent_to_next:
                best_nb = nb
                best_cost = cost[nb]
        path[1] = best_nb
        return path
