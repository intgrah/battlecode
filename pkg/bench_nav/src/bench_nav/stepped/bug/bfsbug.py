"""BFS + Bug1 hybrid — stepped.

Each step, first try local BFS over the 69-cell sensor window. Fall back to
Bug1 circumnavigation if BFS finds nothing strictly better.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import override

from bench_nav.common import INF
from bench_nav.precomputation import COST
from bench_nav.stepped.bug._common import (
    WallFollowState,
    WallStepOutcome,
    bresenham,
    dir_to_goal,
    dist_sq,
    has_los,
    local_bfs,
    make_passable_closures,
    neighbour,
    wall_follow_step,
)
from bench_nav.types import PrecompCtx, Stepped


class _Mode(Enum):
    MOTION = 0
    CIRCUMNAV = 1
    RETURN_TO_LEAVE = 2


def _bfs_next_step(
    pos: tuple[int, int],
    goal: tuple[int, int],
    threshold: int,
    passable: Callable[[int, int], bool],
) -> tuple[int, int] | None:
    parent = local_bfs(pos, passable)
    best: tuple[tuple[int, int], int] | None = None
    for c in parent:
        d = dist_sq(c, goal)
        if d >= threshold:
            continue
        if best is None or d < best[1]:
            best = (c, d)
    if best is None:
        return None
    target = best[0]
    cur = target
    nxt = target
    while cur in parent:
        p = parent[cur]
        if p == pos:
            nxt = cur
            break
        cur = p
    if target == goal or dist_sq(nxt, goal) < threshold:
        return nxt
    return None


class BfsBug(Stepped):
    REQUIRES = frozenset({COST})

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.w = ctx.w
        self.h = ctx.h
        self.cost = ctx[COST]
        self.passable, self.on_map = make_passable_closures(
            ctx.w, ctx.h, self.cost, INF
        )
        self._active_goal: int | None = None
        self._mode = _Mode.MOTION
        self._wf = WallFollowState(
            pos=(0, 0), current_obstacle=(0, 0), obstacle_on_right=True
        )
        self._best_leave: tuple[int, int] = (0, 0)
        self._best_leave_dist_sq = 0
        self._global_min_dist_sq = 0
        self._follow_visited: set[tuple[tuple[int, int], tuple[int, int], bool]] = set()
        self._los_queue: list[tuple[int, int]] = []

    def _reset(self, p: tuple[int, int], g: tuple[int, int]) -> None:
        self._mode = _Mode.MOTION
        self._wf = WallFollowState(pos=p, current_obstacle=p, obstacle_on_right=True)
        self._best_leave = p
        self._best_leave_dist_sq = dist_sq(p, g)
        self._global_min_dist_sq = dist_sq(p, g)
        self._follow_visited.clear()
        self._los_queue.clear()

    @override
    def step(self, pos: int, goal: int) -> int | None:
        w = self.w
        p = (pos % w, pos // w)
        g = (goal % w, goal // w)
        if goal != self._active_goal:
            self._active_goal = goal
            self._reset(p, g)
        if not self.passable(*p) or not self.passable(*g):
            return None
        if p == g:
            return pos

        if self._los_queue:
            nxt = self._los_queue.pop(0)
            return nxt[1] * w + nxt[0]
        if has_los(p, g, self.passable):
            queue = bresenham(p, g)[1:]
            if queue:
                self._los_queue = queue[1:]
                first = queue[0]
                return first[1] * w + first[0]

        if self._mode is _Mode.MOTION:
            threshold = dist_sq(p, g)
        else:
            threshold = min(self._global_min_dist_sq, self._best_leave_dist_sq)
        bfs_next = _bfs_next_step(p, g, threshold, self.passable)
        if bfs_next is not None:
            d2 = dist_sq(bfs_next, g)
            self._global_min_dist_sq = min(self._global_min_dist_sq, d2)
            if self._mode is not _Mode.MOTION:
                self._mode = _Mode.MOTION
                self._follow_visited.clear()
            return bfs_next[1] * w + bfs_next[0]

        if self._mode is _Mode.MOTION:
            d = dir_to_goal(p, g)
            np = neighbour(p, d)
            if self.passable(*np):
                d2 = dist_sq(np, g)
                self._global_min_dist_sq = min(self._global_min_dist_sq, d2)
                return np[1] * w + np[0]
            self._mode = _Mode.CIRCUMNAV
            self._wf = WallFollowState(
                pos=p,
                current_obstacle=neighbour(p, d),
                obstacle_on_right=True,
            )
            self._best_leave = p
            self._best_leave_dist_sq = dist_sq(p, g)
            self._follow_visited.clear()
            self._follow_visited.add(
                (self._wf.pos, self._wf.current_obstacle, self._wf.obstacle_on_right)
            )
            return pos
        if self._mode is _Mode.CIRCUMNAV:
            self._wf.pos = p
            outcome = wall_follow_step(self._wf, self.passable, self.on_map)
            if outcome is WallStepOutcome.SURROUNDED:
                return None
            np = self._wf.pos
            d2 = dist_sq(np, g)
            if d2 < self._best_leave_dist_sq:
                self._best_leave = np
                self._best_leave_dist_sq = d2
            state = (
                self._wf.pos,
                self._wf.current_obstacle,
                self._wf.obstacle_on_right,
            )
            if state in self._follow_visited:
                if self._best_leave_dist_sq >= self._global_min_dist_sq:
                    return None
                self._global_min_dist_sq = self._best_leave_dist_sq
                self._mode = _Mode.RETURN_TO_LEAVE
                self._follow_visited.clear()
                self._follow_visited.add(state)
            else:
                self._follow_visited.add(state)
            return np[1] * w + np[0]
        # RETURN_TO_LEAVE
        if p == self._best_leave:
            self._mode = _Mode.MOTION
            return pos
        self._wf.pos = p
        outcome = wall_follow_step(self._wf, self.passable, self.on_map)
        if outcome is WallStepOutcome.SURROUNDED:
            return None
        np = self._wf.pos
        state = (self._wf.pos, self._wf.current_obstacle, self._wf.obstacle_on_right)
        if state in self._follow_visited:
            return None
        self._follow_visited.add(state)
        return np[1] * w + np[0]
