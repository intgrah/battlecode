from __future__ import annotations

import random
from typing import TYPE_CHECKING

from cambc import Controller, Position
from util import DIR8_DELTA

if TYPE_CHECKING:
    from array import array
    from collections.abc import Callable

    from builder.state import State

from util import INF as _INF

_TARGET_DRIFT_SQ = 25
_CPU_BUDGET = 1729
_TIEBREAK_EPS = 1e-5

_DIR8_DELTA = DIR8_DELTA.copy()
random.shuffle(_DIR8_DELTA)


class AStarSearch:
    def __init__(
        self,
        neighbors: list[tuple[int, int, int]],
        heuristic: Callable[[Position, Position], float],
        cost_grid_attr: str,
        *,
        allow_relaxation: bool = False,
    ) -> None:
        self._neighbors = neighbors
        self._heuristic = heuristic
        self._cost_attr = cost_grid_attr
        self._relax = allow_relaxation

        self._w = 0
        self._h = 0
        self._dist: list[float] = []
        self._visited = bytearray()
        self._prev_visited = bytearray()
        self._q: list[tuple[float, Position]] = []
        self._finished = True
        self._no_path = False
        self._prev_no_path = False
        self._running_target: Position | None = None
        self._prev_target: Position | None = None

    def _init_grid(self, state: State) -> None:
        self._w, self._h = state.w, state.h
        self._dist = [_INF] * (self._w * self._h)

    def _reset(self, state: State) -> None:
        n = state.w * state.h
        if len(self._dist) != n:
            self._init_grid(state)
        self._no_path = False
        self._visited = bytearray((n + 7) // 8)
        self._q = []

    def _cost_grid(self, state: State) -> array[float]:
        return getattr(state, self._cost_attr)

    def _extract_path(
        self, state: State, start: Position, target: Position
    ) -> list[Position]:
        cost = self._cost_grid(state)
        w = self._w
        path: list[Position] = []
        current = start
        while current != target:
            if current in path:
                break
            path.append(current)
            best_dist = _INF
            best = current
            for dx, dy, extra in self._neighbors:
                nx, ny = current.x + dx, current.y + dy
                idx = ny * w + nx
                if (
                    0 <= nx < self._w
                    and 0 <= ny < self._h
                    and (self._prev_visited[idx // 8] & (1 << (idx % 8)))
                    and cost[idx] != _INF
                ):
                    d = self._dist[idx] + extra
                    if d < best_dist:
                        best_dist = d
                        best = Position(nx, ny)
            current = best
        path.append(target)
        return path

    def _run(
        self, state: State, ct: Controller, start: Position, goal: Position
    ) -> bool:
        cost = self._cost_grid(state)
        w = self._w
        dist = self._dist
        visited = self._visited
        neighbors = self._neighbors
        relax = self._relax
        sx, sy = start.x, start.y
        w_bound = self._w
        h_bound = self._h
        # conv_search uses manhattan, move_search uses chebyshev.
        # Branching on an int flag once per call is cheap; branching
        # per-neighbor inside the loop is not.
        is_chebyshev = _HEURISTIC_KIND.get(id(self._heuristic)) == _H_CHEBYSHEV

        gi = goal.y * w + goal.x
        si = sy * w + sx
        dist[gi] = 0
        visited[gi // 8] |= 1 << (gi % 8)

        # Bucket capacity must cover max edge weight + heuristic delta.
        # Bridges add ~8 cost, +2 heuristic swing = ~10. 20 is safe.
        nb_count = 20
        gx, gy = goal.x, goal.y
        if is_chebyshev:
            dx0, dy0 = abs(gx - sx), abs(gy - sy)
            f0 = max(dy0, dx0)
        else:
            f0 = abs(gx - sx) + abs(gy - sy)
        bk: list[list[int]] = [[] for _ in range(nb_count)]
        bk[f0 % nb_count].append(gi)
        cur_f = f0
        emp = 0

        while emp < nb_count:
            bucket = bk[cur_f % nb_count]
            if not bucket:
                cur_f += 1
                emp += 1
                continue
            emp = 0
            for node_i in bucket:
                ny_, nx_ = divmod(node_i, w)
                if is_chebyshev:
                    dxn, dyn = abs(nx_ - sx), abs(ny_ - sy)
                    node_h = max(dyn, dxn)
                else:
                    node_h = abs(nx_ - sx) + abs(ny_ - sy)
                if dist[node_i] + node_h != cur_f:
                    continue
                if node_i == si:
                    return True
                if ct.get_cpu_time_elapsed() > _CPU_BUDGET:
                    return False
                gn = dist[node_i]
                for dx, dy, extra in neighbors:
                    nx = nx_ + dx
                    ny = ny_ + dy
                    if nx < 0 or nx >= w_bound or ny < 0 or ny >= h_bound:
                        continue
                    ni = ny * w + nx
                    seen = visited[ni // 8] & (1 << (ni % 8))
                    if relax and not seen:
                        dist[ni] = _INF
                    if not relax and seen:
                        continue
                    visited[ni // 8] |= 1 << (ni % 8)
                    mc = cost[ni]
                    if mc >= _INF:
                        continue
                    nd = gn + mc + extra
                    if relax and nd >= dist[ni]:
                        continue
                    dist[ni] = nd
                    if is_chebyshev:
                        dxn, dyn = abs(nx - sx), abs(ny - sy)
                        h_val = max(dyn, dxn)
                    else:
                        h_val = abs(nx - sx) + abs(ny - sy)
                    f = nd + h_val
                    bk[f % nb_count].append(ni)
            bk[cur_f % nb_count] = []
            cur_f += 1

        self._no_path = True
        return True

    def search(
        self, state: State, ct: Controller, start: Position, target: Position
    ) -> list[Position] | None:
        if (
            self._finished
            or self._running_target is None
            or target.distance_squared(self._running_target) > _TARGET_DRIFT_SQ
        ):
            self._reset(state)
        else:
            target = self._running_target

        self._running_target = target
        self._finished = self._run(state, ct, start, target)

        if self._finished:
            self._prev_visited = self._visited
            self._prev_target = target
            self._prev_no_path = self._no_path

        if self._prev_target is None:
            return None
        diff = target.distance_squared(self._prev_target)
        if diff <= _TARGET_DRIFT_SQ and diff < start.distance_squared(target):
            if self._no_path:
                return None
            return self._extract_path(state, start, target)
        return None

    def search_blocked(
        self, state: State, ct: Controller, start: Position, goal: Position
    ) -> list[Position] | None:
        cost = self._cost_grid(state)
        saved: list[tuple[int, float]] = []
        for pos in ct.get_nearby_tiles(2):
            if ct.get_tile_builder_bot_id(pos) is not None and pos != start:
                idx = pos.y * state.w + pos.x
                saved.append((idx, cost[idx]))
                cost[idx] = _INF
        result = self.search(state, ct, start, goal)
        for idx, val in saved:
            cost[idx] = val
        return result

    @property
    def no_path(self) -> bool:
        return self._prev_no_path


def _chebyshev(a: Position, b: Position) -> float:
    dx = abs(a.x - b.x)
    dy = abs(a.y - b.y)
    return max(dx, dy) + _TIEBREAK_EPS * (dx + dy)


def _manhattan(a: Position, b: Position) -> float:
    dx = abs(a.x - b.x)
    dy = abs(a.y - b.y)
    return (dx + dy) + _TIEBREAK_EPS * (dx + dy)


# Heuristic kind flags for the inlined inner loop. Using an int flag
# instead of a function call avoids Python call dispatch in the hot
# path. Must match the `_chebyshev` / `_manhattan` functions above
# exactly (modulo the eps-tiebreak which int() truncates anyway).
_H_MANHATTAN = 0
_H_CHEBYSHEV = 1
_HEURISTIC_KIND: dict = {
    id(_manhattan): _H_MANHATTAN,
    id(_chebyshev): _H_CHEBYSHEV,
}


DIAG_WEIGHT = 4
# Bridge edges: cardinal ±2/±3 plus the four 2-tile diagonals. 12
# neighbors total — a compromise between the full 24-neighbor r²≤9
# set (too slow on CPython's per-op budget) and cardinal-only (too
# restrictive on maps where walls run at 45°). Covers straight walls
# and most diagonal obstacles.
COST_BRIDGE_EXTRA = 7
_BRIDGE_DELTAS = [
    (2, 0), (-2, 0), (0, 2), (0, -2),
    (3, 0), (-3, 0), (0, 3), (0, -3),
    (2, 2), (2, -2), (-2, 2), (-2, -2),
]

_MOVE_NEIGHBORS = [(dx, dy, 0) for dx, dy in _DIR8_DELTA]
_CONV_NEIGHBORS = [
    (1, 0, 0),
    (-1, 0, 0),
    (0, 1, 0),
    (0, -1, 0),
    (1, 1, DIAG_WEIGHT),
    (1, -1, DIAG_WEIGHT),
    (-1, 1, DIAG_WEIGHT),
    (-1, -1, DIAG_WEIGHT),
] + [(dx, dy, COST_BRIDGE_EXTRA) for dx, dy in _BRIDGE_DELTAS]
random.shuffle(_CONV_NEIGHBORS)

move_search = AStarSearch(_MOVE_NEIGHBORS, _chebyshev, "cost_grid")
conv_search = AStarSearch(
    _CONV_NEIGHBORS, _manhattan, "conveyor_cost_grid", allow_relaxation=True
)


def pathfind(
    state: State, ct: Controller, start: Position, target: Position
) -> list[Position] | None:
    return move_search.search(state, ct, start, target)


def pathfind_blocked(
    state: State, ct: Controller, start: Position, goal: Position
) -> list[Position] | None:
    return move_search.search_blocked(state, ct, start, goal)


def conv_pathfind(
    state: State, ct: Controller, start: Position, target: Position
) -> list[Position] | None:
    return conv_search.search(state, ct, start, target)


def conv_pathfind_blocked(
    state: State, ct: Controller, start: Position, goal: Position
) -> list[Position] | None:
    return conv_search.search_blocked(state, ct, start, goal)


def conv_unreachable(target: Position) -> bool:
    return conv_search.no_path and conv_search._prev_target == target
