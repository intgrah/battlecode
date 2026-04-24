from __future__ import annotations

from collections import deque
from typing import override

from bench_nav.common import CR, Path_, extract_parent
from bench_nav.precomputation import COST, PNB
from bench_nav.types import (
    PrecompCtx,
    Spsp,
)

assert CR == 1


class Bfs01(Spsp):
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
        q = deque([start])
        popleft = q.popleft
        appendleft = q.appendleft
        append = q.append
        while q:
            node = popleft()
            if node == goal:
                return extract_parent(parent, start, goal)
            for nb in pnb[node]:
                if parent[nb] == -1:
                    parent[nb] = node
                    if cost[nb] == 1:
                        appendleft(nb)
                    else:
                        append(nb)
        return None
