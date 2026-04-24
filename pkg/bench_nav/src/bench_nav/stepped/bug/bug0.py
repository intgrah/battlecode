"""Bug0 — classical greedy wall-follow, stepped."""

from __future__ import annotations

from typing import override

from bench_nav.common import INF
from bench_nav.precomputation import COST
from bench_nav.stepped.bug._common import (
    WallFollowState,
    WallStepOutcome,
    dir_to_goal,
    dist_sq,
    make_passable_closures,
    neighbour,
    wall_follow_step,
)
from bench_nav.types import PrecompCtx, Stepped


class Bug0(Stepped):
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
        self._follow = False
        self._wf = WallFollowState(
            pos=(0, 0), current_obstacle=(0, 0), obstacle_on_right=True
        )
        self._hit_dist_sq = 0

    def _init(self, pos: tuple[int, int], g: tuple[int, int]) -> None:
        self._follow = False
        self._wf = WallFollowState(
            pos=pos, current_obstacle=pos, obstacle_on_right=True
        )
        self._hit_dist_sq = dist_sq(pos, g)

    @override
    def step(self, pos: int, goal: int) -> int | None:
        w = self.w
        p = (pos % w, pos // w)
        g = (goal % w, goal // w)
        if goal != self._active_goal:
            self._active_goal = goal
            self._init(p, g)
        if not self.passable(*p) or not self.passable(*g):
            return None
        if p == g:
            return pos

        if not self._follow:
            d = dir_to_goal(p, g)
            np = neighbour(p, d)
            if self.passable(*np):
                return np[1] * w + np[0]
            self._follow = True
            self._wf = WallFollowState(
                pos=p,
                current_obstacle=neighbour(p, d),
                obstacle_on_right=True,
            )
            self._hit_dist_sq = dist_sq(p, g)
            return pos
        # follow mode
        d = dir_to_goal(p, g)
        np = neighbour(p, d)
        if self.passable(*np) and dist_sq(np, g) < self._hit_dist_sq:
            self._follow = False
            return np[1] * w + np[0]
        self._wf.pos = p
        outcome = wall_follow_step(self._wf, self.passable, self.on_map)
        if outcome is WallStepOutcome.SURROUNDED:
            return None
        np = self._wf.pos
        return np[1] * w + np[0]
