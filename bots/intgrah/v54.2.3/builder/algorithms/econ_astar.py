from __future__ import annotations

import random
from typing import TYPE_CHECKING

from cambc import Controller, Position

if TYPE_CHECKING:
    from array import array
    from collections.abc import Callable

    from builder.state import State

from util import INF as _INF

_TARGET_DRIFT_SQ = 25
_CPU_BUDGET = 1729
_TIEBREAK_EPS = 1e-5


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
        self._pw = 0
        self._ph = 0
        self._pad = 0
        self._flat_neighbors: list[tuple[int, int]] = []
        self._dist: list[int] = []
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
        self._pw, self._ph = state.pw, state.ph
        self._pad = state.pad
        pn = self._pw * self._ph
        self._dist = [_INF] * pn
        self._flat_neighbors = [
            (dy * self._pw + dx, extra) for dx, dy, extra in self._neighbors
        ]

    def _reset(self, state: State) -> None:
        pn = state.pw * state.ph
        if len(self._dist) != pn:
            self._init_grid(state)
        self._no_path = False
        self._visited = bytearray((pn + 7) // 8)
        self._q = []

    def _cost_grid(self, state: State) -> array[float]:
        return getattr(state, self._cost_attr)

    def _extract_path(
        self, state: State, start: Position, target: Position
    ) -> list[Position]:
        cost = self._cost_grid(state)
        pw = self._pw
        pad = self._pad
        flat_neighbors = self._flat_neighbors
        prev_visited = self._prev_visited
        dist = self._dist
        path: list[Position] = []
        current = start
        while current != target:
            if current in path:
                break
            path.append(current)
            best_dist = _INF
            best = current
            ci = (current.y + pad) * pw + (current.x + pad)
            for off, extra in flat_neighbors:
                idx = ci + off
                if not (prev_visited[idx >> 3] & (1 << (idx & 7))):
                    continue
                if cost[idx] >= _INF:
                    continue
                d = dist[idx] + extra
                if d < best_dist:
                    best_dist = d
                    y_p, x_p = divmod(idx, pw)
                    best = Position(x_p - pad, y_p - pad)
            current = best
        path.append(target)
        return path

    def _run(
        self, state: State, ct: Controller, start: Position, goal: Position
    ) -> bool:
        cost = self._cost_grid(state)
        pw = self._pw
        pad = self._pad
        dist = self._dist
        visited = self._visited
        flat_neighbors = self._flat_neighbors
        relax = self._relax
        sx_p = start.x + pad
        sy_p = start.y + pad
        gx_p = goal.x + pad
        gy_p = goal.y + pad

        gi = gy_p * pw + gx_p
        si = sy_p * pw + sx_p
        dist[gi] = 0
        visited[gi >> 3] |= 1 << (gi & 7)

        nb_count = 24
        f0 = abs(gx_p - sx_p) + abs(gy_p - sy_p)
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
                ny_, nx_ = divmod(node_i, pw)
                node_h = abs(nx_ - sx_p) + abs(ny_ - sy_p)
                if dist[node_i] + node_h != cur_f:
                    continue
                if node_i == si:
                    return True
                if ct.get_cpu_time_elapsed() > _CPU_BUDGET:
                    return False
                gn = dist[node_i]
                for off, extra in flat_neighbors:
                    ni = node_i + off
                    mc = cost[ni]
                    if mc >= _INF:
                        continue
                    seen = visited[ni >> 3] & (1 << (ni & 7))
                    if relax and not seen:
                        dist[ni] = _INF
                    if not relax and seen:
                        continue
                    visited[ni >> 3] |= 1 << (ni & 7)
                    nd = gn + mc + extra
                    if relax and nd >= dist[ni]:
                        continue
                    dist[ni] = nd
                    ny2, nx2 = divmod(ni, pw)
                    h_val = abs(nx2 - sx_p) + abs(ny2 - sy_p)
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
        pw = state.pw
        pad = state.pad
        saved: list[tuple[int, int]] = []
        for pos in ct.get_nearby_tiles():
            if ct.get_tile_builder_bot_id(pos) is not None and pos != start:
                idx = (pos.y + pad) * pw + (pos.x + pad)
                saved.append((idx, cost[idx]))
                cost[idx] = _INF
        result = self.search(state, ct, start, goal)
        for idx, val in saved:
            cost[idx] = val
        return result

    @property
    def no_path(self) -> bool:
        return self._prev_no_path


def _manhattan(a: Position, b: Position) -> float:
    dx = abs(a.x - b.x)
    dy = abs(a.y - b.y)
    return (dx + dy) + _TIEBREAK_EPS * (dx + dy)


DIAG_WEIGHT = 4
COST_BRIDGE_EXTRA = 7
_BRIDGE_DELTAS = [
    (dx, dy)
    for dx in range(-3, 4)
    for dy in range(-3, 4)
    if 3 <= dx * dx + dy * dy <= 9
]
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

conv_search = AStarSearch(
    _CONV_NEIGHBORS, _manhattan, "conveyor_cost_grid", allow_relaxation=True
)


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
