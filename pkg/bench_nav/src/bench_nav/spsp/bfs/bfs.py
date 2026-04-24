from __future__ import annotations

from typing import override

from bench_nav.common import Path_, extract_parent
from bench_nav.precomputation import PNB
from bench_nav.types import (
    PrecompCtx,
    Spsp,
)


def _bfs(n: int, pnb: list[list[int]], start: int, goal: int) -> Path_:
    parent = [-1] * n
    parent[start] = start
    q = [start]
    append = q.append
    for node in q:
        for nb in pnb[node]:
            if parent[nb] == -1:
                parent[nb] = node
                if nb == goal:
                    return extract_parent(parent, start, goal)
                append(nb)
    return None


class BfsSpsp(Spsp):
    REQUIRES = frozenset({PNB})

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.n = ctx.n
        self.pnb = ctx[PNB]

    @override
    def plan(self, start: int, goal: int) -> Path_:
        return _bfs(self.n, self.pnb, start, goal)
