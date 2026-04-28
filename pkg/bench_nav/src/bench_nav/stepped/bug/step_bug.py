"""StepBug — Bug1 with m-line shortcut, plan once.

Plans CW and CCW perimeter walks; picks shorter arc to leave point.
"""

from __future__ import annotations

from typing import override

from bench_nav.precomputation import COST
from bench_nav.stepped.bug._planner import bug1_plan
from bench_nav.stepped.dp_step import dp_step
from bench_nav.types import PrecompCtx, Stepped


class StepBug(Stepped):
    REQUIRES = frozenset({COST})

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.w = ctx.w
        self.h = ctx.h
        self.n = ctx.n
        self.cost = ctx[COST]
        self._active_goal: int | None = None
        self._path_idx: list[int] = [-1] * ctx.n
        self._has_path: bool = False

    @override
    def step(self, pos: int, goal: int) -> int | None:
        if goal != self._active_goal:
            self._active_goal = goal
            self._path_idx[:] = [-1] * self.n
            raw = bug1_plan(self.cost, self.w, self.h, pos, goal)
            if raw is None:
                self._has_path = False
                return None
            for i, c in enumerate(raw):
                self._path_idx[c] = i
            self._has_path = True
        if not self._has_path:
            return None
        return dp_step(self.w, self.cost, self.h, pos, self._path_idx)
