"""Bug2 with bounded per-step planner iterations and persistent state."""

from __future__ import annotations

from collections.abc import Iterator
from typing import override

from bench_nav.precomputation import COST
from bench_nav.stepped.bug._planner import bug2_plan_iter
from bench_nav.stepped.dp_step import dp_step
from bench_nav.types import AlgoName, PrecompCtx, Stepped

_BUDGET = 25


class Bug2Bounded(Stepped):
    NAME = AlgoName("bug-bug2-bounded")
    REQUIRES = frozenset({COST})

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.w = ctx.w
        self.h = ctx.h
        self.n = ctx.n
        self.cost = ctx[COST]
        self._active_goal: int | None = None
        self._gen: Iterator[None] | None = None
        self._gen_done: bool = False
        self._path_idx: list[int] = [-1] * ctx.n

    @override
    def step(self, pos: int, goal: int) -> int | None:
        if goal != self._active_goal:
            self._active_goal = goal
            self._path_idx[:] = [-1] * self.n
            self._path_idx[pos] = 0
            self._gen = bug2_plan_iter(self.cost, self.w, self.h, pos, goal, self._path_idx)
            self._gen_done = False
        if not self._gen_done and self._gen is not None:
            for _ in range(_BUDGET):
                try:
                    next(self._gen)
                except StopIteration:
                    self._gen_done = True
                    break
        return dp_step(self.w, self.cost, self.h, pos, self._path_idx)
