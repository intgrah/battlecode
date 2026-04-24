"""StepBug — step-at-a-time Bug1 with Bug2 m-line candidates, short-arc select, stepped.

One wall-follow step per turn. During the walk we track Bug1's closest-to-goal
cell and Bug2's m-line crossings; on state-cycle termination pick the shortest
committed arc (forward CW or ACW) from hit to the best leave point.
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

_K = 4


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
    CIRCUM_CW = 1
    CIRCUM_ACW = 2
    WALK_ARC = 3


class StepBug(Stepped):
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
        self._s: tuple[int, int] = (0, 0)
        self._global_min = 0
        self._mline_dx = 0
        self._mline_dy = 0
        self._mline_tol = 0
        self._mline_d0 = 0
        self._wf = WallFollowState(
            pos=(0, 0), current_obstacle=(0, 0), obstacle_on_right=True
        )
        self._hit_pos: tuple[int, int] = (0, 0)
        self._hit_d = 0
        self._blocked_dir = 0
        self._cw_perim: list[tuple[int, int]] = []
        self._cw_b1_idx = 0
        self._cw_b1_d = 1 << 30
        self._cw_b2: int | None = None
        self._cw_closed = False
        self._acw_perim: list[tuple[int, int]] = []
        self._acw_b1_idx = 0
        self._acw_b1_d = 1 << 30
        self._acw_b2: int | None = None
        self._acw_closed = False
        self._seen: dict[int, int] = {}
        self._version = 0
        self._arc: list[tuple[int, int]] = []
        self._arc_idx = 0
        self._arc_end_d = 0

    def _reset(self, p: tuple[int, int], g: tuple[int, int]) -> None:
        self._mode = _Mode.MOTION
        self._s = p
        self._global_min = dist_sq(p, g)
        self._mline_dx = g[0] - p[0]
        self._mline_dy = g[1] - p[1]
        self._mline_tol = max(abs(self._mline_dx), abs(self._mline_dy)) // 2
        self._mline_d0 = dist_sq(p, g)
        self._cw_perim = []
        self._acw_perim = []
        self._seen = {}
        self._version = 0
        self._arc = []
        self._arc_idx = 0

    def _on_mline(self, p: tuple[int, int]) -> bool:
        cx = p[0] - self._s[0]
        cy = p[1] - self._s[1]
        if abs(cy * self._mline_dx - cx * self._mline_dy) > self._mline_tol:
            return False
        return (
            cx * self._mline_dx + cy * self._mline_dy > 0
            and dist_sq(p, (self._s[0] + self._mline_dx, self._s[1] + self._mline_dy))
            < self._mline_d0
        )

    def _start_walk(self, obstacle_on_right: bool) -> None:
        self._wf = WallFollowState(
            pos=self._hit_pos,
            current_obstacle=neighbour(self._hit_pos, self._blocked_dir),
            obstacle_on_right=obstacle_on_right,
        )
        if obstacle_on_right:
            self._cw_perim = [self._hit_pos]
            self._cw_b1_idx = 0
            self._cw_b1_d = self._hit_d
        else:
            self._acw_perim = [self._hit_pos]
            self._acw_b1_idx = 0
            self._acw_b1_d = self._hit_d
        self._version += 1
        self._seen.clear()
        self._seen[_state_idx(self.w, self._wf)] = self._version

    def _finish_circum(self, g: tuple[int, int]) -> bool:
        best: tuple[int, list[tuple[int, int]], int] | None = None

        def cheb_weighted(leave: tuple[int, int]) -> int:
            dx = abs(leave[0] - g[0])
            dy = abs(leave[1] - g[1])
            hi, lo = max(dx, dy), min(dx, dy)
            return 15 * hi + 6 * lo

        def consider(arc_cells: list[tuple[int, int]], end_d: int) -> None:
            nonlocal best
            if not arc_cells:
                return
            score = 10 * len(arc_cells) + cheb_weighted(arc_cells[-1])
            if best is None or score < best[0]:
                best = (score, arc_cells, end_d)

        def eval_walk(
            perim: list[tuple[int, int]],
            b1_idx: int,
            b1_d: int,
            _b2: int | None,
            gmin: int,
        ) -> None:
            if b1_d < gmin and b1_idx > 0:
                consider(list(perim[1 : b1_idx + 1]), b1_d)

        eval_walk(
            self._cw_perim,
            self._cw_b1_idx,
            self._cw_b1_d,
            self._cw_b2,
            self._global_min,
        )
        if self._cw_closed and len(self._cw_perim) >= 2:
            n = len(self._cw_perim)
            rev = [self._hit_pos]
            for i in range(n - 2, 0, -1):
                rev.append(self._cw_perim[i])
            rev.append(self._hit_pos)
            r_b1_idx = 0
            r_b1_d = self._hit_d
            r_b2: int | None = None
            for i, c in enumerate(rev):
                d2 = dist_sq(c, g)
                if d2 < r_b1_d:
                    r_b1_d = d2
                    r_b1_idx = i
                if i > 0 and self._on_mline(c) and r_b2 is None:
                    r_b2 = i
            eval_walk(rev, r_b1_idx, r_b1_d, r_b2, self._global_min)
        eval_walk(
            self._acw_perim,
            self._acw_b1_idx,
            self._acw_b1_d,
            self._acw_b2,
            self._global_min,
        )

        if best is None:
            return False
        _, arc_cells, end_d = best
        self._arc = arc_cells
        self._arc_idx = 0
        self._arc_end_d = end_d
        self._mode = _Mode.WALK_ARC
        return True

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

        while True:
            if self._mode is _Mode.MOTION:
                d = dir_to_goal(p, g)
                np = neighbour(p, d)
                if self.passable(*np):
                    d2 = dist_sq(np, g)
                    self._global_min = min(self._global_min, d2)
                    return np[1] * w + np[0]
                # enter_circum
                self._mode = _Mode.CIRCUM_CW
                self._hit_pos = p
                self._hit_d = dist_sq(p, g)
                self._blocked_dir = d
                self._cw_closed = False
                self._cw_b1_d = 1 << 30
                self._cw_b2 = None
                self._acw_closed = False
                self._acw_b1_d = 1 << 30
                self._acw_b2 = None
                self._start_walk(True)
                continue
            if self._mode in (_Mode.CIRCUM_CW, _Mode.CIRCUM_ACW):
                finished = False
                for _ in range(_K):
                    cw = self._mode is _Mode.CIRCUM_CW
                    outcome = wall_follow_step(self._wf, self.passable, self.on_map)
                    if outcome is WallStepOutcome.SURROUNDED:
                        if cw:
                            self._start_walk(False)
                            self._mode = _Mode.CIRCUM_ACW
                            continue
                        if not self._finish_circum(g):
                            return None
                        finished = True
                        break
                    d2 = dist_sq(self._wf.pos, g)
                    mline = self._on_mline(self._wf.pos)
                    if cw:
                        self._cw_perim.append(self._wf.pos)
                        k_idx = len(self._cw_perim) - 1
                        if d2 < self._cw_b1_d:
                            self._cw_b1_d = d2
                            self._cw_b1_idx = k_idx
                        if mline and self._cw_b2 is None:
                            self._cw_b2 = k_idx
                    else:
                        self._acw_perim.append(self._wf.pos)
                        k_idx = len(self._acw_perim) - 1
                        if d2 < self._acw_b1_d:
                            self._acw_b1_d = d2
                            self._acw_b1_idx = k_idx
                        if mline and self._acw_b2 is None:
                            self._acw_b2 = k_idx
                    idx = _state_idx(w, self._wf)
                    if self._seen.get(idx) == self._version:
                        if cw:
                            self._cw_closed = self._wf.pos == self._hit_pos
                            self._start_walk(False)
                            self._mode = _Mode.CIRCUM_ACW
                        else:
                            self._acw_closed = self._wf.pos == self._hit_pos
                            if not self._finish_circum(g):
                                return None
                            finished = True
                        break
                    self._seen[idx] = self._version
                if finished:
                    continue
                # Bot doesn't move during circumnavigation — this is sim-only.
                return pos
            # WALK_ARC
            if self._arc_idx >= len(self._arc):
                self._global_min = self._arc_end_d
                self._mode = _Mode.MOTION
                self._arc = []
                continue
            out_pos = self._arc[self._arc_idx]
            self._arc_idx += 1
            if self._arc_idx >= len(self._arc):
                self._global_min = self._arc_end_d
                self._mode = _Mode.MOTION
                self._arc = []
            return out_pos[1] * w + out_pos[0]
