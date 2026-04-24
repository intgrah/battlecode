"""FastBug — bounded look-ahead Bug1, stepped.

Bot physically wall-follows one cell per step; internally a simulation runs
K=128 wall-follow steps ahead each round. Once sim detects a full perimeter
cycle, bot commits to the short arc (forward or backward) from its current
perim position to the perim's closest-to-goal cell.
"""

from __future__ import annotations

from enum import Enum
from typing import override

from bench_nav.common import INF
from bench_nav.precomputation import COST
from bench_nav.stepped.bug._common import (
    DIRS,
    WallFollowState,
    WallStepOutcome,
    dir_to_goal,
    dist_sq,
    make_passable_closures,
    neighbour,
    wall_follow_step,
)
from bench_nav.types import PrecompCtx, Stepped

_K = 128


def _dir_of(delta: tuple[int, int]) -> int:
    for i, d in enumerate(DIRS):
        if d == delta:
            return i
    return 0


def _state_idx(w: int, wf: WallFollowState) -> int:
    pos_idx = wf.pos[1] * w + wf.pos[0]
    obs_dir = _dir_of(
        (
            wf.current_obstacle[0] - wf.pos[0],
            wf.current_obstacle[1] - wf.pos[1],
        )
    )
    side = 1 if wf.obstacle_on_right else 0
    return pos_idx * 16 + obs_dir * 2 + side


class _Mode(Enum):
    MOTION = 0
    CIRCUM = 1
    WALK_ARC = 2


class FastBug(Stepped):
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
        self._sim_wf = WallFollowState(
            pos=(0, 0), current_obstacle=(0, 0), obstacle_on_right=True
        )
        self._hit_pos: tuple[int, int] = (0, 0)
        self._perim: list[tuple[int, int]] = []
        self._sim_done = False
        self._sim_closed = False
        self._best_idx = 0
        self._best_d = 0
        self._bot_idx = 0
        self._seen: dict[int, int] = {}
        self._version = 0
        self._arc_target_idx = 0
        self._arc_forward = True
        self._arc_wrap = False

    def _reset(self) -> None:
        self._mode = _Mode.MOTION
        self._perim = []
        self._sim_done = False
        self._sim_closed = False
        self._bot_idx = 0
        self._seen = {}
        self._version = 0

    @override
    def step(self, pos: int, goal: int) -> int | None:
        w = self.w
        p = (pos % w, pos // w)
        g = (goal % w, goal // w)
        if goal != self._active_goal:
            self._active_goal = goal
            self._reset()
        if not self.passable(*p) or not self.passable(*g):
            return None
        if p == g:
            return pos

        if self._mode is _Mode.MOTION:
            d = dir_to_goal(p, g)
            np = neighbour(p, d)
            if self.passable(*np):
                return np[1] * w + np[0]
            # enter_circum
            self._mode = _Mode.CIRCUM
            self._hit_pos = p
            self._sim_wf = WallFollowState(
                pos=p,
                current_obstacle=neighbour(p, d),
                obstacle_on_right=True,
            )
            self._perim = [p]
            self._sim_done = False
            self._sim_closed = False
            self._best_d = dist_sq(p, g)
            self._best_idx = 0
            self._bot_idx = 0
            self._version += 1
            self._seen = {_state_idx(w, self._sim_wf): self._version}
            return pos
        if self._mode is _Mode.CIRCUM:
            # sim_advance
            for _ in range(_K):
                if self._sim_done:
                    break
                outcome = wall_follow_step(self._sim_wf, self.passable, self.on_map)
                if outcome is WallStepOutcome.SURROUNDED:
                    self._sim_done = True
                    break
                self._perim.append(self._sim_wf.pos)
                k = len(self._perim) - 1
                d2 = dist_sq(self._sim_wf.pos, g)
                if d2 < self._best_d:
                    self._best_d = d2
                    self._best_idx = k
                idx = _state_idx(w, self._sim_wf)
                if self._seen.get(idx) == self._version:
                    self._sim_done = True
                    self._sim_closed = self._sim_wf.pos == self._hit_pos
                    break
                self._seen[idx] = self._version
            out_pos = p
            if self._bot_idx + 1 < len(self._perim):
                self._bot_idx += 1
                out_pos = self._perim[self._bot_idx]
            if self._sim_done:
                if self._best_d >= dist_sq(self._hit_pos, g):
                    return None
                n = len(self._perim)
                bi, ki = self._bot_idx, self._best_idx
                closed = self._sim_closed and n >= 2
                big = 1 << 62
                fwd_direct = ki - bi if ki >= bi else big
                bwd_direct = bi - ki if ki <= bi else big
                fwd_wrap = ((n - 1 - bi) + ki) if (closed and ki < bi) else big
                bwd_wrap = (bi + (n - 1 - ki)) if (closed and ki > bi) else big
                options = (
                    (fwd_direct, True, False),
                    (bwd_direct, False, False),
                    (fwd_wrap, True, True),
                    (bwd_wrap, False, True),
                )
                _, self._arc_forward, self._arc_wrap = min(options, key=lambda t: t[0])
                self._arc_target_idx = self._best_idx
                self._mode = _Mode.WALK_ARC
            return out_pos[1] * w + out_pos[0]
        # WALK_ARC
        if self._bot_idx == self._arc_target_idx:
            self._mode = _Mode.MOTION
            return pos
        n = len(self._perim)
        if self._arc_forward:
            self._bot_idx += 1
            if self._arc_wrap and self._bot_idx >= n - 1:
                self._bot_idx = 0
        elif self._bot_idx == 0:
            if self._arc_wrap:
                self._bot_idx = n - 2
        else:
            self._bot_idx -= 1
        out_pos = self._perim[self._bot_idx]
        if self._bot_idx == self._arc_target_idx:
            self._mode = _Mode.MOTION
        return out_pos[1] * w + out_pos[0]
