from __future__ import annotations

import random
from typing import TYPE_CHECKING

from cambc import Controller, Position
from util import DIR8_DELTA

if TYPE_CHECKING:
    from array import array
    from collections.abc import Callable

    from builder import Builder

from util import INF as _INF

_TARGET_DRIFT_SQ = 25
_CPU_BUDGET = 1729
_TIEBREAK_EPS = 1e-5

_DIR8_DELTA = list(DIR8_DELTA)
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
        self._pw = 0
        self._ph = 0
        self._pad = 0
        # Flat-index neighbor offsets in the PADDED grid layout.
        # Precomputed once `pw` is known (at _init_grid) so the hot
        # loop does `ni = node_i + off` with no per-neighbor delta
        # math and no bounds check (out-of-map positions land on the
        # INF-filled padding ring).
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

    def _init_grid(self, state: Builder) -> None:
        self._w, self._h = state.w, state.h
        self._pw, self._ph = state.pw, state.ph
        self._pad = state.pad
        pn = self._pw * self._ph
        self._dist = [_INF] * pn
        # Bake in the padded-row stride now that pw is known.
        self._flat_neighbors = [
            (dy * self._pw + dx, extra) for dx, dy, extra in self._neighbors
        ]

    def _reset(self, state: Builder) -> None:
        pn = state.pw * state.ph
        if len(self._dist) != pn:
            self._init_grid(state)
        self._no_path = False
        self._visited = bytearray((pn + 7) // 8)
        self._q = []

    def _cost_grid(self, state: Builder) -> array[int]:
        return getattr(state, self._cost_attr)

    def _extract_path(
        self, state: Builder, start: Position, target: Position
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
        self, state: Builder, ct: Controller, start: Position, goal: Position
    ) -> bool:
        cost = self._cost_grid(state)
        pw = self._pw
        pad = self._pad
        dist = self._dist
        visited = self._visited
        flat_neighbors = self._flat_neighbors
        relax = self._relax
        # Work entirely in PADDED coordinates — start/goal indices,
        # neighbor lookups, and heuristic all use (x+pad, y+pad).
        # The INF border means the inner loop never needs a bounds
        # check; out-of-map neighbors land on padding and get
        # rejected by the `mc >= _INF` guard that was already there.
        sx_p = start.x + pad
        sy_p = start.y + pad
        gx_p = goal.x + pad
        gy_p = goal.y + pad
        # conv_search uses manhattan, move_search uses chebyshev.
        is_chebyshev = _HEURISTIC_KIND.get(id(self._heuristic)) == _H_CHEBYSHEV

        gi = gy_p * pw + gx_p
        si = sy_p * pw + sx_p
        dist[gi] = 0
        visited[gi >> 3] |= 1 << (gi & 7)

        # Bucket capacity must STRICTLY exceed max (edge_cost + h_diff).
        # With ore tiles capped at 10, max edge = 10 + COST_BRIDGE_EXTRA=7
        # + h_diff=3 = 20. nb_count=24 gives safe margin. Smaller
        # nb_count also means cheaper per-cycle iteration over empty
        # buckets in the outer `while` loop.
        nb_count = 24
        if is_chebyshev:
            dx0, dy0 = abs(gx_p - sx_p), abs(gy_p - sy_p)
            f0 = max(dx0, dy0)
        else:
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
                if is_chebyshev:
                    dxn, dyn = abs(nx_ - sx_p), abs(ny_ - sy_p)
                    node_h = max(dxn, dyn)
                else:
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
                    if is_chebyshev:
                        dxn, dyn = abs(nx2 - sx_p), abs(ny2 - sy_p)
                        h_val = max(dxn, dyn)
                    else:
                        h_val = abs(nx2 - sx_p) + abs(ny2 - sy_p)
                    f = nd + h_val
                    bk[f % nb_count].append(ni)
            bk[cur_f % nb_count] = []
            cur_f += 1

        self._no_path = True
        return True

    def search(
        self, state: Builder, ct: Controller, start: Position, target: Position
    ) -> list[Position]:
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
            return []
        diff = target.distance_squared(self._prev_target)
        if diff <= _TARGET_DRIFT_SQ and diff < start.distance_squared(target):
            if self._no_path:
                return []
            return self._extract_path(state, start, target)
        return []

    def search_blocked(
        self, state: Builder, ct: Controller, start: Position, goal: Position
    ) -> list[Position] | None:
        cost = self._cost_grid(state)
        pw = state.pw
        pad = state.pad
        saved: list[tuple[int, int]] = []
        for pos in ct.get_nearby_tiles(2):
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
# Bridge neighborhood: every (dx, dy) with 2 ≤ dx²+dy² ≤ 9. 20 deltas.
# Excludes d²=1 (cardinal, already in _CONV_NEIGHBORS as cheap
# conveyor edges) AND d²=2 (the four ±(1,1) diagonals, already in
# _CONV_NEIGHBORS as DIAG_WEIGHT=4 conveyor edges). Those diagonals
# used to be duplicated here as cost-7 bridge edges — A* always
# picked the cheaper cost-5 diagonal, so the bridge copies were
# dead work. Dropping them = 4 fewer per-node iterations.
COST_BRIDGE_EXTRA = 7
_BRIDGE_DELTAS = [
    (dx, dy)
    for dx in range(-3, 4)
    for dy in range(-3, 4)
    if 2 <= dx * dx + dy * dy <= 9
]

_MOVE_NEIGHBORS = [(dx, dy, 0) for dx, dy in _DIR8_DELTA]
_CONV_NEIGHBORS = [
    (1, 0, 0),
    (-1, 0, 0),
    (0, 1, 0),
    (0, -1, 0),
] + [(dx, dy, COST_BRIDGE_EXTRA) for dx, dy in _BRIDGE_DELTAS]
random.shuffle(_CONV_NEIGHBORS)


def _turret_blocked_tiles(
    state: Builder, ct: Controller, near: Position
) -> set[Position]:
    """Return the set of tiles within king-move of `near` that are
    inside an enemy turret's current attack pattern — movement
    should avoid stepping onto these.

    Only considers turrets the bot can actually see (in vision).
    We scan `state.nearby_buildings` (already computed this turn)
    rather than querying the controller again.

    Covers:
    - Gunners: forward ray along their facing direction, up to r²≤13
    - Sentinels: 1-king-wide forward arc, up to r²≤32
    - Launchers / breach: vision-radius hazard zone (r²≤2 for
      launcher pickup, r²≤13 for breach) — treat as blocked if
      any of our 8 neighbours is within their attack envelope.

    Keeps the check cheap: only tiles within 3 of `near` are
    candidates (we only care about our next step).
    """
    # Quick-exit: on most turns there are no visible enemy turrets,
    # so we shouldn't waste time scanning. `nearest_enemy_turret`
    # is already tracked and cleared per turn in state_update_map.
    if state.nearest_enemy_turret is None:
        return set()
    my_team = state.my_team
    blocked: set[Position] = set()
    for i in state.nearby_buildings:
        bp = state.pos(i)
        bld = state.get_building(i)
        if bld is None or getattr(bld, "team", None) == my_team:
            continue
        etype = type(bld).__name__
        if etype == "BuildingGunner":
            # Forward ray along facing direction.
            direction = getattr(bld, "direction", None)
            if direction is None:
                continue
            cur = bp
            for _ in range(4):  # r²≤13 → max 3 tiles cardinal
                cur = cur.add(direction)
                if cur.distance_squared(near) > 2:
                    break
                blocked.add(cur)
        elif etype == "BuildingSentinel":
            # Sentinels hit within 1 king-move of the forward line.
            direction = getattr(bld, "direction", None)
            if direction is None:
                continue
            cur = bp
            for _ in range(6):  # r²≤32 → up to ~5.6 tiles
                cur = cur.add(direction)
                if cur.distance_squared(bp) > 32:
                    break
                if cur.distance_squared(near) > 4:
                    continue
                blocked.add(cur)
                # +1 king-move band around the line.
                for d in _DIR8_DELTA:
                    blocked.add(Position(cur.x + d[0], cur.y + d[1]))
    return blocked


# Empirically, allow_relaxation=True is load-bearing for path
# quality, not just bucket-overflow protection. Theory says Dial's
# bucket A* with a consistent heuristic shouldn't need it, but every
# relax-off sweep regressed to ~35-40% (vs 80% with relax on).
# Leaving it on.
conv_search = AStarSearch(
    _CONV_NEIGHBORS, _manhattan, "conveyor_cost_grid", allow_relaxation=True
)


def conv_pathfind(
    state: Builder, ct: Controller, start: Position, target: Position
) -> list[Position]:
    return conv_search.search(state, ct, start, target)


def conv_unreachable(target: Position) -> bool:
    return conv_search.no_path and conv_search._prev_target == target
