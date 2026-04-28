"""A* (dial + Chebyshev heuristic) stepped — plan once, follow with dp_step."""

from __future__ import annotations

from collections import deque
from typing import override

from bench_nav.common import INF, extract_parent
from bench_nav.precomputation import COST, PNB
from bench_nav.stepped.dp_step import dp_step
from bench_nav.types import PrecompCtx, Stepped


def _astar_plan(
    w: int, n: int, cost: list[int], pnb: list[list[int]], si: int, gi: int
) -> list[int] | None:
    gx = gi % w
    gy = gi // w
    g = [INF] * n
    g[si] = 0
    parent = [-1] * n
    parent[si] = si
    h_start = max(abs(si % w - gx), abs(si // w - gy))
    bk: list[deque[int]] = [deque() for _ in range(5)]
    bk[h_start % 5].append(si)
    f = h_start
    emp = 0
    while emp < 5:
        bki = bk[f % 5]
        if bki:
            emp = 0
            popleft = bki.popleft
            while bki:
                node = popleft()
                g_node = g[node]
                if g_node + max(abs(node % w - gx), abs(node // w - gy)) != f:
                    continue
                if node == gi:
                    return extract_parent(parent, si, gi)
                for nb in pnb[node]:
                    nd = g_node + cost[nb]
                    if nd < g[nb]:
                        g[nb] = nd
                        parent[nb] = node
                        h_nb = max(abs(nb % w - gx), abs(nb // w - gy))
                        bk[(nd + h_nb) % 5].append(nb)
        else:
            emp += 1
        f += 1
    return None


class AstarStepped(Stepped):
    REQUIRES = frozenset({COST, PNB})

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.w = ctx.w
        self.h = ctx.h
        self.n = ctx.n
        self.cost = ctx[COST]
        self.pnb = ctx[PNB]
        self._active_goal: int | None = None
        self._path_idx: list[int] = [-1] * ctx.n
        self._has_path: bool = False

    @override
    def step(self, pos: int, goal: int) -> int | None:
        if goal != self._active_goal:
            self._active_goal = goal
            self._path_idx[:] = [-1] * self.n
            raw = _astar_plan(self.w, self.h * self.w, self.cost, self.pnb, pos, goal)
            if raw is None:
                self._has_path = False
                return None
            for i, c in enumerate(raw):
                self._path_idx[c] = i
            self._has_path = True
        if not self._has_path:
            return None
        return dp_step(self.w, self.cost, self.h, pos, self._path_idx)
