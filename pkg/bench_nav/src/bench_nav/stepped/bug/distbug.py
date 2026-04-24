"""DistBug — range-sensor bug, stepped."""

from __future__ import annotations

from enum import Enum
from math import sqrt
from typing import override

from bench_nav.common import INF
from bench_nav.precomputation import COST
from bench_nav.stepped.bug._common import (
    DIRS,
    VISION_R_SQ,
    WallFollowState,
    WallStepOutcome,
    dir_to_goal,
    dist_sq,
    make_passable_closures,
    neighbour,
    wall_follow_step,
)
from bench_nav.types import PrecompCtx, Stepped

_STEP = 1.0


class _Mode(Enum):
    MOTION = 0
    FOLLOW = 1


class DistBug(Stepped):
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
        self._d_min = 0.0
        self._follow_visited: set[tuple[tuple[int, int], tuple[int, int], bool]] = set()

    def _reset(self, p: tuple[int, int], g: tuple[int, int]) -> None:
        self._mode = _Mode.MOTION
        self._wf = WallFollowState(pos=p, current_obstacle=p, obstacle_on_right=True)
        self._d_min = sqrt(dist_sq(p, g))
        self._follow_visited.clear()

    def _free_distance_to_goal(self, cur: tuple[int, int], g: tuple[int, int]) -> float:
        d = dir_to_goal(cur, g)
        dx, dy = DIRS[d]
        p = cur
        while True:
            nxt = (p[0] + dx, p[1] + dy)
            if dist_sq(cur, nxt) > VISION_R_SQ:
                break
            if not self.passable(*nxt):
                break
            p = nxt
        return sqrt(dist_sq(cur, p))

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

        if self._mode is _Mode.MOTION:
            d = dir_to_goal(p, g)
            np = neighbour(p, d)
            if self.passable(*np):
                nd = sqrt(dist_sq(np, g))
                self._d_min = min(self._d_min, nd)
                return np[1] * w + np[0]
            self._mode = _Mode.FOLLOW
            self._wf = WallFollowState(
                pos=p,
                current_obstacle=neighbour(p, d),
                obstacle_on_right=True,
            )
            self._follow_visited.clear()
            self._follow_visited.add(
                (self._wf.pos, self._wf.current_obstacle, self._wf.obstacle_on_right)
            )
            return pos
        # FOLLOW
        d_leave = sqrt(dist_sq(p, g))
        f = self._free_distance_to_goal(p, g)
        if d_leave - f <= self._d_min - _STEP:
            self._mode = _Mode.MOTION
            return pos
        self._wf.pos = p
        outcome = wall_follow_step(self._wf, self.passable, self.on_map)
        if outcome is WallStepOutcome.SURROUNDED:
            return None
        np = self._wf.pos
        nd = sqrt(dist_sq(np, g))
        self._d_min = min(self._d_min, nd)
        state = (self._wf.pos, self._wf.current_obstacle, self._wf.obstacle_on_right)
        if state in self._follow_visited:
            return None
        self._follow_visited.add(state)
        return np[1] * w + np[0]
