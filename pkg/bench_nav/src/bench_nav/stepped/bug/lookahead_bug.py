"""LookaheadBug — simulation-based lookahead with BFS direction validator, stepped.

Maintains a simulated `bug_pos` that runs up to 6 steps ahead of the real
agent each turn. Simulation is greedy with bug-mode fallback. A small BFS
flood (3 iters) from `bug_pos` ranks the agent's 8 neighbours; the best
strict-improvement direction wins. Trail replay / centroid / any-passable
fallbacks if no direction qualifies.

Two variants: LookaheadBug (sensor-limited, pessimistic) and
LookaheadBugFullMap (all cells pre-discovered).
"""

from __future__ import annotations

from typing import override

from bench_nav.common import INF
from bench_nav.precomputation import COST
from bench_nav.stepped.bug._common import (
    DIRS,
    VISION_R_SQ,
    dist_sq,
    sensed_cells,
)
from bench_nav.types import AlgoName, PrecompCtx, Stepped

_SIM_STEPS = 6
_MAX_PATH_BACKUP = 50
_BFS_ITERS = 3
_INF_DIST = 100_000


def _dir_to_cell(from_: tuple[int, int], to: tuple[int, int]) -> int:
    dx = (to[0] > from_[0]) - (to[0] < from_[0])
    dy = (to[1] > from_[1]) - (to[1] < from_[1])
    match (dx, dy):
        case (0, -1):
            return 0
        case (1, -1):
            return 1
        case (1, 0):
            return 2
        case (1, 1):
            return 3
        case (0, 1):
            return 4
        case (-1, 1):
            return 5
        case (-1, 0):
            return 6
        case (-1, -1):
            return 7
        case _:
            return 0


class _LookaheadBase(Stepped):
    REQUIRES = frozenset({COST})
    _full_map = False

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.w = ctx.w
        self.h = ctx.h
        self.cost = ctx[COST]
        self._active_goal: int | None = None
        n = ctx.w * ctx.h
        self._discovered = bytearray(n)
        self._pos: tuple[int, int] = (0, 0)
        self._bug_pos: tuple[int, int] = (0, 0)
        self._bug_dir = 0
        self._clockwise = False
        self._should_guess_rotation = True
        self._best_bug_dist = 1 << 30
        self._should_bug = False
        self._bug_path: list[tuple[int, int]] = []

    def _reset(self, p: tuple[int, int]) -> None:
        n = self.w * self.h
        self._discovered = bytearray(b"\x01" * n if self._full_map else n)
        self._pos = p
        self._bug_pos = p
        self._bug_dir = 0
        self._clockwise = False
        self._should_guess_rotation = True
        self._best_bug_dist = 1 << 30
        self._should_bug = False
        self._bug_path = []

    def _idx(self, x: int, y: int) -> int | None:
        if 0 <= x < self.w and 0 <= y < self.h:
            return y * self.w + x
        return None

    def _believed_passable(self, p: tuple[int, int]) -> bool:
        if p == self._pos:
            return True
        i = self._idx(*p)
        if i is None:
            return False
        return bool(self._discovered[i]) and self.cost[i] < INF

    def _in_vision(self, p: tuple[int, int]) -> bool:
        return dist_sq(self._pos, p) <= VISION_R_SQ

    def _sense(self, cur_pos: tuple[int, int]) -> None:
        for c in sensed_cells(cur_pos):
            i = self._idx(*c)
            if i is not None:
                self._discovered[i] = 1

    def _reset_bug(self) -> None:
        self._best_bug_dist = 1 << 30
        self._should_bug = False
        self._bug_pos = self._pos
        self._bug_dir = 0
        self._should_guess_rotation = True
        self._clockwise = False
        self._bug_path.clear()

    def _append_trail(self) -> None:
        if len(self._bug_path) >= _MAX_PATH_BACKUP:
            return
        if self._bug_path and self._bug_path[-1] == self._bug_pos:
            return
        self._bug_path.append(self._bug_pos)

    def _resync_bug_pos(self) -> None:
        for i in range(len(self._bug_path) - 1, -1, -1):
            if self._in_vision(self._bug_path[i]):
                self._bug_pos = self._bug_path[i]
                return
        self._reset_bug()

    def _greedy_step(self, g: tuple[int, int]) -> bool:
        best_dist = dist_sq(self._bug_pos, g)
        best_loc = self._bug_pos
        for di in range(8):
            new_loc = (self._bug_pos[0] + DIRS[di][0], self._bug_pos[1] + DIRS[di][1])
            if not self._in_vision(new_loc):
                return True
            if not self._believed_passable(new_loc):
                continue
            nd = dist_sq(new_loc, g)
            if nd < best_dist:
                best_dist = nd
                best_loc = new_loc
        if best_loc != self._bug_pos:
            self._bug_pos = best_loc
        else:
            self._best_bug_dist = dist_sq(self._bug_pos, g)
            self._bug_dir = _dir_to_cell(self._bug_pos, g)
            self._should_bug = True
        return False

    def _bug_step(self, g: tuple[int, int]) -> bool:
        if self._should_guess_rotation:
            self._should_guess_rotation = False
            dir_l = self._bug_dir
            for _ in range(8):
                test = (
                    self._bug_pos[0] + DIRS[dir_l][0],
                    self._bug_pos[1] + DIRS[dir_l][1],
                )
                if self._believed_passable(test):
                    break
                dir_l = (dir_l + 7) % 8
            dir_r = self._bug_dir
            for _ in range(8):
                test = (
                    self._bug_pos[0] + DIRS[dir_r][0],
                    self._bug_pos[1] + DIRS[dir_r][1],
                )
                if self._believed_passable(test):
                    break
                dir_r = (dir_r + 1) % 8
            loc_l = (
                self._bug_pos[0] + DIRS[dir_l][0],
                self._bug_pos[1] + DIRS[dir_l][1],
            )
            loc_r = (
                self._bug_pos[0] + DIRS[dir_r][0],
                self._bug_pos[1] + DIRS[dir_r][1],
            )
            self._clockwise = dist_sq(loc_r, g) < dist_sq(loc_l, g)

        current_loc: tuple[int, int] | None = None
        new_loc = (
            self._bug_pos[0] + DIRS[self._bug_dir][0],
            self._bug_pos[1] + DIRS[self._bug_dir][1],
        )
        if not self._in_vision(new_loc):
            return True
        if self._believed_passable(new_loc):
            current_loc = new_loc

        if current_loc is None:
            for _ in range(8):
                self._bug_dir = (
                    (self._bug_dir + 1) % 8
                    if self._clockwise
                    else (self._bug_dir + 7) % 8
                )
                probe = (
                    self._bug_pos[0] + DIRS[self._bug_dir][0],
                    self._bug_pos[1] + DIRS[self._bug_dir][1],
                )
                if not self._in_vision(probe):
                    return True
                if self._believed_passable(probe):
                    current_loc = probe
                    break

        if current_loc is not None and current_loc != self._bug_pos:
            self._bug_pos = current_loc
            self._bug_dir = (
                (self._bug_dir + 7) % 8 if self._clockwise else (self._bug_dir + 1) % 8
            )
            d = dist_sq(self._bug_pos, g)
            if d < self._best_bug_dist:
                self._should_bug = False
        return False

    def _validator_on_direction(self) -> list[int]:
        result = [_INF_DIST] * 9
        nb_positions: list[tuple[int, int] | None] = [None] * 9
        for di in range(8):
            p = (self._pos[0] + DIRS[di][0], self._pos[1] + DIRS[di][1])
            if self._idx(*p) is not None:
                nb_positions[di] = p
        nb_positions[8] = self._pos
        for di, np_opt in enumerate(nb_positions):
            if np_opt is not None and np_opt == self._bug_pos:
                result[di] = 0
        visited: set[tuple[int, int]] = {self._bug_pos}
        frontier: list[tuple[int, int]] = [self._bug_pos]
        for iteration in range(1, _BFS_ITERS + 1):
            next_frontier: list[tuple[int, int]] = []
            for cx, cy in frontier:
                for dd in range(8):
                    nx = cx + DIRS[dd][0]
                    ny = cy + DIRS[dd][1]
                    nc = (nx, ny)
                    if nc in visited:
                        continue
                    if not self._believed_passable(nc):
                        continue
                    visited.add(nc)
                    next_frontier.append(nc)
                    for di, np_opt in enumerate(nb_positions):
                        if (
                            np_opt is not None
                            and np_opt == nc
                            and iteration < result[di]
                        ):
                            result[di] = iteration
            frontier = next_frontier
            if not frontier:
                break
            if all(
                np_opt is None or result[di] != _INF_DIST
                for di, np_opt in enumerate(nb_positions)
            ):
                break
        return result

    @override
    def step(self, pos: int, goal: int) -> int | None:
        w = self.w
        p = (pos % w, pos // w)
        g = (goal % w, goal // w)
        if goal != self._active_goal:
            self._active_goal = goal
            self._reset(p)
        if self.cost[pos] >= INF or self.cost[goal] >= INF:
            return None
        if p == g:
            return pos

        self._pos = p
        self._sense(p)

        if dist_sq(p, g) <= 2:
            d = _dir_to_cell(p, g)
            np = (p[0] + DIRS[d][0], p[1] + DIRS[d][1])
            if self._believed_passable(np):
                return np[1] * w + np[0]

        self._resync_bug_pos()
        if len(self._bug_path) >= _MAX_PATH_BACKUP:
            self._reset_bug()

        for _ in range(_SIM_STEPS):
            if dist_sq(self._bug_pos, g) <= 2:
                break
            stop = self._bug_step(g) if self._should_bug else self._greedy_step(g)
            if stop:
                break
            self._append_trail()

        bfs_dists = self._validator_on_direction()
        center_bfs = bfs_dists[8]
        center_bug_dist = dist_sq(p, self._bug_pos)

        best_dir: int | None = None
        backup_dir: int | None = None
        best_dist = _INF_DIST
        best_bug_d = 1 << 30

        for d in range(8):
            n_pos = (p[0] + DIRS[d][0], p[1] + DIRS[d][1])
            if not self._believed_passable(n_pos):
                continue
            backup_dir = d
            dist_val = bfs_dists[d]
            bug_d = dist_sq(n_pos, self._bug_pos)
            if dist_val >= center_bfs:
                continue
            if dist_val == center_bfs and bug_d >= center_bug_dist:
                continue
            if dist_val < best_dist or (dist_val == best_dist and bug_d < best_bug_d):
                best_dir = d
                best_dist = dist_val
                best_bug_d = bug_d

        chosen_dir = best_dir

        if chosen_dir is None and len(self._bug_path) >= 2:
            for i in range(len(self._bug_path) - 2, -1, -1):
                if self._bug_path[i] != p:
                    continue
                next_pos = self._bug_path[i + 1]
                candidate = _dir_to_cell(p, next_pos)
                stepc = (p[0] + DIRS[candidate][0], p[1] + DIRS[candidate][1])
                if stepc != next_pos or not self._believed_passable(next_pos):
                    continue
                chosen_dir = candidate
                break

        if chosen_dir is None and self._bug_path:
            half = self._bug_path[len(self._bug_path) // 2 :]
            if half:
                sx = sum(pt[0] for pt in half)
                sy = sum(pt[1] for pt in half)
                avg = (sx // len(half), sy // len(half))
                candidate = _dir_to_cell(p, avg)
                stepc = (p[0] + DIRS[candidate][0], p[1] + DIRS[candidate][1])
                if self._believed_passable(stepc):
                    chosen_dir = candidate
                self._reset_bug()

        if chosen_dir is None:
            chosen_dir = backup_dir

        if chosen_dir is not None:
            np = (p[0] + DIRS[chosen_dir][0], p[1] + DIRS[chosen_dir][1])
            if self._believed_passable(np):
                return np[1] * w + np[0]
        return None


class LookaheadBug(_LookaheadBase):
    NAME = AlgoName("bug-lookahead")
    _full_map = False


class LookaheadBugFullMap(_LookaheadBase):
    NAME = AlgoName("bug-lookahead-fullmap")
    _full_map = True
