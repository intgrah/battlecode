"""PrunedBug — plan-ahead Bug, returns cached path one step at a time.

Compute the full path on the first step() (using Bug1/Bug2/DistBug policies
with cycle pruning), then emit cells along it. This makes the first step's
time the per-query cost; subsequent steps are O(1) list lookups — the
classic "pay once, then walk" pattern, which blows the per-turn budget on
the first step but gives cheap follow-ups.
"""

from __future__ import annotations

from collections.abc import Callable
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
from bench_nav.types import AlgoName, PrecompCtx, Stepped


def _prune_cycles(path: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    idx: dict[tuple[int, int], int] = {}
    for c in path:
        if c in idx:
            k = idx[c]
            while len(out) > k + 1:
                popped = out.pop()
                if popped in idx and idx[popped] == len(out):
                    del idx[popped]
        else:
            idx[c] = len(out)
            out.append(c)
    return out


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


def _bug2_path_with(
    w: int,
    h: int,
    passable: Callable[[int, int], bool],
    on_map: Callable[[int, int], bool],
    start: tuple[int, int],
    goal: tuple[int, int],
    obstacle_on_right: bool,
) -> list[tuple[int, int]] | None:
    safety_cap = 2 * w * h + 16
    seen: dict[int, int] = {}
    version = 0
    path: list[tuple[int, int]] = [start]
    pos = start
    dx_t = goal[0] - start[0]
    dy_t = goal[1] - start[1]
    tol = max(abs(dx_t), abs(dy_t)) // 2
    d_start_goal = dist_sq(start, goal)

    def on_mline(p: tuple[int, int]) -> bool:
        cx = p[0] - start[0]
        cy = p[1] - start[1]
        if abs(cy * dx_t - cx * dy_t) > tol:
            return False
        return cx * dx_t + cy * dy_t > 0 and dist_sq(p, goal) < d_start_goal

    while True:
        if pos == goal:
            return path
        if len(path) > safety_cap:
            return None
        d = dir_to_goal(pos, goal)
        np = neighbour(pos, d)
        if passable(*np):
            pos = np
            path.append(pos)
            continue
        hit_pos = pos
        hit_d = dist_sq(hit_pos, goal)
        wf = WallFollowState(
            pos=hit_pos,
            current_obstacle=neighbour(hit_pos, d),
            obstacle_on_right=obstacle_on_right,
        )
        version += 1
        seen.clear()
        seen[_state_idx(w, wf)] = version
        while True:
            outcome = wall_follow_step(wf, passable, on_map)
            if outcome is WallStepOutcome.SURROUNDED:
                return None
            path.append(wf.pos)
            if on_mline(wf.pos) and dist_sq(wf.pos, goal) < hit_d:
                pos = wf.pos
                break
            idx = _state_idx(w, wf)
            if seen.get(idx) == version:
                return None
            seen[idx] = version
            if len(path) > safety_cap:
                return None


def _bug2_path(
    w: int,
    h: int,
    passable: Callable[[int, int], bool],
    on_map: Callable[[int, int], bool],
    start: tuple[int, int],
    goal: tuple[int, int],
) -> list[tuple[int, int]] | None:
    cw = _bug2_path_with(w, h, passable, on_map, start, goal, True)
    ccw = _bug2_path_with(w, h, passable, on_map, start, goal, False)
    if cw is None:
        return ccw
    if ccw is None:
        return cw
    return cw if len(cw) <= len(ccw) else ccw


def _distbug_path_with(
    w: int,
    h: int,
    passable: Callable[[int, int], bool],
    on_map: Callable[[int, int], bool],
    start: tuple[int, int],
    goal: tuple[int, int],
    obstacle_on_right: bool,
) -> list[tuple[int, int]] | None:
    safety_cap = 2 * w * h + 16
    seen: dict[int, int] = {}
    version = 0
    path: list[tuple[int, int]] = [start]
    pos = start
    d_min = dist_sq(start, goal)
    while True:
        if pos == goal:
            return path
        if len(path) > safety_cap:
            return None
        d = dir_to_goal(pos, goal)
        np = neighbour(pos, d)
        if passable(*np):
            pos = np
            path.append(pos)
            d2 = dist_sq(pos, goal)
            d_min = min(d_min, d2)
            continue
        hit_pos = pos
        wf = WallFollowState(
            pos=hit_pos,
            current_obstacle=neighbour(hit_pos, d),
            obstacle_on_right=obstacle_on_right,
        )
        version += 1
        seen.clear()
        seen[_state_idx(w, wf)] = version
        while True:
            rdx, rdy = DIRS[dir_to_goal(wf.pos, goal)]
            ray_end = wf.pos
            while True:
                nx = ray_end[0] + rdx
                ny = ray_end[1] + rdy
                if not passable(nx, ny):
                    break
                ray_end = (nx, ny)
                if ray_end == goal:
                    break
            d_after = dist_sq(ray_end, goal)
            if ray_end != wf.pos and d_after < d_min:
                p = wf.pos
                while p != ray_end:
                    p = (p[0] + rdx, p[1] + rdy)
                    path.append(p)
                pos = ray_end
                d_min = d_after
                break
            outcome = wall_follow_step(wf, passable, on_map)
            if outcome is WallStepOutcome.SURROUNDED:
                return None
            path.append(wf.pos)
            d2 = dist_sq(wf.pos, goal)
            d_min = min(d_min, d2)
            idx = _state_idx(w, wf)
            if seen.get(idx) == version:
                return None
            seen[idx] = version
            if len(path) > safety_cap:
                return None


def _distbug_path(
    w: int,
    h: int,
    passable: Callable[[int, int], bool],
    on_map: Callable[[int, int], bool],
    start: tuple[int, int],
    goal: tuple[int, int],
) -> list[tuple[int, int]] | None:
    cw = _distbug_path_with(w, h, passable, on_map, start, goal, True)
    ccw = _distbug_path_with(w, h, passable, on_map, start, goal, False)
    if cw is None:
        return ccw
    if ccw is None:
        return cw
    return cw if len(cw) <= len(ccw) else ccw


def _walk_perim(
    w: int,
    h: int,
    passable: Callable[[int, int], bool],
    on_map: Callable[[int, int], bool],
    hit_pos: tuple[int, int],
    blocked_dir: int,
    goal: tuple[int, int],
    obstacle_on_right: bool,
    seen: dict[int, int],
    version: int,
    safety_cap: int,
) -> tuple[list[tuple[int, int]], int, int, bool] | None:
    wf = WallFollowState(
        pos=hit_pos,
        current_obstacle=neighbour(hit_pos, blocked_dir),
        obstacle_on_right=obstacle_on_right,
    )
    seen[_state_idx(w, wf)] = version
    perim: list[tuple[int, int]] = [hit_pos]
    best_leave_d = dist_sq(hit_pos, goal)
    best_leave_idx = 0
    while True:
        outcome = wall_follow_step(wf, passable, on_map)
        if outcome is WallStepOutcome.SURROUNDED:
            return None
        perim.append(wf.pos)
        d2 = dist_sq(wf.pos, goal)
        if d2 < best_leave_d:
            best_leave_d = d2
            best_leave_idx = len(perim) - 1
        idx = _state_idx(w, wf)
        if seen.get(idx) == version:
            break
        seen[idx] = version
        if len(perim) > safety_cap:
            return None
    closed = perim[-1] == hit_pos
    return perim, best_leave_idx, best_leave_d, closed


def _best_arc(
    perim: list[tuple[int, int]], best_leave_idx: int, closed: bool
) -> list[tuple[int, int]]:
    forward_len = best_leave_idx
    backward_len = len(perim) - 1 - best_leave_idx
    if closed and backward_len < forward_len:
        out: list[tuple[int, int]] = []
        for i in range(len(perim) - 2, best_leave_idx, -1):
            out.append(perim[i])
        out.append(perim[best_leave_idx])
        return out
    return list(perim[1 : best_leave_idx + 1])


def _bug1_path(
    w: int,
    h: int,
    passable: Callable[[int, int], bool],
    on_map: Callable[[int, int], bool],
    start: tuple[int, int],
    goal: tuple[int, int],
) -> list[tuple[int, int]] | None:
    safety_cap = 2 * w * h + 16
    seen: dict[int, int] = {}
    version = 0
    path: list[tuple[int, int]] = [start]
    pos = start
    global_min = dist_sq(start, goal)
    while True:
        if pos == goal:
            return path
        if len(path) > safety_cap:
            return None
        d = dir_to_goal(pos, goal)
        np = neighbour(pos, d)
        if passable(*np):
            pos = np
            path.append(pos)
            d2 = dist_sq(pos, goal)
            global_min = min(global_min, d2)
            continue
        hit_pos = pos
        blocked_dir = d
        version += 1
        seen.clear()
        cw = _walk_perim(
            w,
            h,
            passable,
            on_map,
            hit_pos,
            blocked_dir,
            goal,
            True,
            seen,
            version,
            safety_cap,
        )
        if cw is None:
            return None
        cw_perim, cw_idx, cw_d, cw_closed = cw
        if cw_closed:
            if cw_d >= global_min:
                return None
            new_min = cw_d
            arc = _best_arc(cw_perim, cw_idx, True)
        else:
            version += 1
            seen.clear()
            acw = _walk_perim(
                w,
                h,
                passable,
                on_map,
                hit_pos,
                blocked_dir,
                goal,
                False,
                seen,
                version,
                safety_cap,
            )
            if acw is None:
                return None
            acw_perim, acw_idx, acw_d, acw_closed = acw
            cw_ok = cw_d < global_min
            acw_ok = acw_d < global_min
            if not cw_ok and not acw_ok:
                return None
            if cw_ok and not acw_ok:
                new_min = cw_d
                arc = _best_arc(cw_perim, cw_idx, False)
            elif not cw_ok and acw_ok:
                new_min = acw_d
                arc = _best_arc(acw_perim, acw_idx, acw_closed)
            else:
                a = _best_arc(cw_perim, cw_idx, False)
                b = _best_arc(acw_perim, acw_idx, acw_closed)
                if len(a) <= len(b):
                    new_min = cw_d
                    arc = a
                else:
                    new_min = acw_d
                    arc = b
        path.extend(arc)
        pos = arc[-1]
        global_min = new_min


def _best_of(
    candidates: list[list[tuple[int, int]] | None],
) -> list[tuple[int, int]] | None:
    best: list[tuple[int, int]] | None = None
    for c in candidates:
        if c is None:
            continue
        p = _prune_cycles(c)
        if len(p) <= 1:
            continue
        if best is None or len(p) < len(best):
            best = p
    return best


class _PrunedBase(Stepped):
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
        self._path: list[int] = []
        self._idx = 0

    def _compute(
        self, s: tuple[int, int], g: tuple[int, int]
    ) -> list[tuple[int, int]] | None:
        raise NotImplementedError

    @override
    def step(self, pos: int, goal: int) -> int | None:
        w = self.w
        p = (pos % w, pos // w)
        g = (goal % w, goal // w)
        if goal != self._active_goal:
            self._active_goal = goal
            if not self.passable(*p) or not self.passable(*g):
                self._path = []
                return None
            raw = self._compute(p, g)
            if raw is None:
                self._path = []
                return None
            pruned = _prune_cycles(raw)
            self._path = [c[1] * w + c[0] for c in pruned]
            self._idx = 1 if self._path and self._path[0] == pos else 0
        if not self._path:
            return None
        if pos == goal:
            return pos
        if self._idx >= len(self._path):
            return None
        nxt = self._path[self._idx]
        self._idx += 1
        return nxt


class PrunedBug1(_PrunedBase):
    NAME = AlgoName("bug-pruned-bug1")

    @override
    def _compute(
        self, s: tuple[int, int], g: tuple[int, int]
    ) -> list[tuple[int, int]] | None:
        return _bug1_path(self.w, self.h, self.passable, self.on_map, s, g)


class PrunedBug2(_PrunedBase):
    NAME = AlgoName("bug-pruned-bug2")

    @override
    def _compute(
        self, s: tuple[int, int], g: tuple[int, int]
    ) -> list[tuple[int, int]] | None:
        return _bug2_path(self.w, self.h, self.passable, self.on_map, s, g)


class PrunedDistBug(_PrunedBase):
    NAME = AlgoName("bug-pruned-distbug")

    @override
    def _compute(
        self, s: tuple[int, int], g: tuple[int, int]
    ) -> list[tuple[int, int]] | None:
        return _distbug_path(self.w, self.h, self.passable, self.on_map, s, g)


class PrunedBestB1B2(_PrunedBase):
    NAME = AlgoName("bug-pruned-best-b1-b2")

    @override
    def _compute(
        self, s: tuple[int, int], g: tuple[int, int]
    ) -> list[tuple[int, int]] | None:
        best = _best_of(
            [
                _bug1_path(self.w, self.h, self.passable, self.on_map, s, g),
                _bug2_path(self.w, self.h, self.passable, self.on_map, s, g),
            ]
        )
        return best


class PrunedBestB1Db(_PrunedBase):
    NAME = AlgoName("bug-pruned-best-b1-db")

    @override
    def _compute(
        self, s: tuple[int, int], g: tuple[int, int]
    ) -> list[tuple[int, int]] | None:
        return _best_of(
            [
                _bug1_path(self.w, self.h, self.passable, self.on_map, s, g),
                _distbug_path(self.w, self.h, self.passable, self.on_map, s, g),
            ]
        )


class PrunedBestOf3(_PrunedBase):
    NAME = AlgoName("bug-pruned-best-of-3")

    @override
    def _compute(
        self, s: tuple[int, int], g: tuple[int, int]
    ) -> list[tuple[int, int]] | None:
        return _best_of(
            [
                _bug1_path(self.w, self.h, self.passable, self.on_map, s, g),
                _bug2_path(self.w, self.h, self.passable, self.on_map, s, g),
                _distbug_path(self.w, self.h, self.passable, self.on_map, s, g),
            ]
        )
