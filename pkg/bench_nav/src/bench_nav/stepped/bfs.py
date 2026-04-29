"""BFS stepped variants. Two BFS planners (cardinal+forced-diagonal, 8-connected),
each with three step optimisers (raw, hop, cost)."""

from __future__ import annotations

from typing import override

from bench_nav.common import INF, extract_parent
from bench_nav.precomputation import COST, PNB, PNB_FD, PNB_SKIP
from bench_nav.stepped.dp_step import dp_step, dp_step_hop
from bench_nav.types import AlgoName, PrecompCtx, Stepped


def _bfs_plan(n: int, pnb: list[list[int]], start: int, goal: int) -> list[int] | None:
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


def _bfs_skip_plan(
    n: int,
    pnb: list[list[int]],
    pnb_push: list[list[int]],
    pnb_set: list[list[int]],
    cost: list[int],
    start: int,
    goal: int,
) -> list[int] | None:
    dist = [INF] * n
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


class _BfsFdBase(Stepped):
    REQUIRES = frozenset({COST, PNB_FD})

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.w = ctx.w
        self.h = ctx.h
        self.n = ctx.n
        self.cost = ctx[COST]
        self.pnb = ctx[PNB_FD]
        self._active_goal: int | None = None
        self._path: list[int] = []
        self._path_idx: list[int] = [-1] * ctx.n

    def _replan(self, pos: int, goal: int) -> bool:
        self._active_goal = goal
        raw = _bfs_plan(self.n, self.pnb, pos, goal)
        if raw is None:
            self._path = []
            self._path_idx[:] = [-1] * self.n
            return False
        self._path = raw
        for i in range(self.n):
            self._path_idx[i] = -1
        for i, c in enumerate(raw):
            self._path_idx[c] = i
        return True


class _Bfs8Base(Stepped):
    REQUIRES = frozenset({COST, PNB, PNB_SKIP})

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.w = ctx.w
        self.h = ctx.h
        self.n = ctx.n
        self.cost = ctx[COST]
        self.pnb = ctx[PNB]
        self.pnb_push, self.pnb_set = ctx[PNB_SKIP]
        self._active_goal: int | None = None
        self._path: list[int] = []
        self._path_idx: list[int] = [-1] * ctx.n

    def _replan(self, pos: int, goal: int) -> bool:
        self._active_goal = goal
        raw = _bfs_skip_plan(
            self.n, self.pnb, self.pnb_push, self.pnb_set, self.cost, pos, goal
        )
        if raw is None:
            self._path = []
            self._path_idx[:] = [-1] * self.n
            return False
        self._path = raw
        for i in range(self.n):
            self._path_idx[i] = -1
        for i, c in enumerate(raw):
            self._path_idx[c] = i
        return True


class BfsFdRaw(_BfsFdBase):
    NAME = AlgoName("bfs-fd-raw")

    @override
    def step(self, pos: int, goal: int) -> int | None:
        if goal != self._active_goal and not self._replan(pos, goal):
            return None
        i = self._path_idx[pos]
        if i < 0 or i + 1 >= len(self._path):
            return None
        return self._path[i + 1]


class BfsFdHop(_BfsFdBase):
    NAME = AlgoName("bfs-fd-hop")

    @override
    def step(self, pos: int, goal: int) -> int | None:
        if goal != self._active_goal and not self._replan(pos, goal):
            return None
        if not self._path:
            return None
        return dp_step_hop(self.w, self.cost, self.h, pos, self._path_idx)


class BfsFdCost(_BfsFdBase):
    NAME = AlgoName("bfs-fd-cost")

    @override
    def step(self, pos: int, goal: int) -> int | None:
        if goal != self._active_goal and not self._replan(pos, goal):
            return None
        if not self._path:
            return None
        return dp_step(self.w, self.cost, self.h, pos, self._path_idx)


class Bfs8Raw(_Bfs8Base):
    NAME = AlgoName("bfs-8-raw")

    @override
    def step(self, pos: int, goal: int) -> int | None:
        if goal != self._active_goal and not self._replan(pos, goal):
            return None
        i = self._path_idx[pos]
        if i < 0 or i + 1 >= len(self._path):
            return None
        return self._path[i + 1]


class Bfs8Hop(_Bfs8Base):
    NAME = AlgoName("bfs-8-hop")

    @override
    def step(self, pos: int, goal: int) -> int | None:
        if goal != self._active_goal and not self._replan(pos, goal):
            return None
        if not self._path:
            return None
        return dp_step_hop(self.w, self.cost, self.h, pos, self._path_idx)


class Bfs8Cost(_Bfs8Base):
    NAME = AlgoName("bfs-8-cost")

    @override
    def step(self, pos: int, goal: int) -> int | None:
        if goal != self._active_goal and not self._replan(pos, goal):
            return None
        if not self._path:
            return None
        return dp_step(self.w, self.cost, self.h, pos, self._path_idx)
