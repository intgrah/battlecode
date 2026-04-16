from __future__ import annotations

import heapq
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

    def _init_grid(self, state: State) -> None:
        self._w, self._h = state.w, state.h
        self._pw, self._ph = state.pw, state.ph
        self._pad = state.pad
        pn = self._pw * self._ph
        self._dist = [_INF] * pn
        # Bake in the padded-row stride now that pw is known.
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
    state: State, ct: Controller, near: Position
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
    my_team = ct.get_team()
    blocked: set[Position] = set()
    for bp in state.nearby_buildings:
        bld = state.get_building(bp)
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


class NavBfs:
    """Backward-BFS movement pathfinder.

    Runs BFS from the goal backward to fill a distance field over
    all reachable tiles. Each subsequent turn (while the goal is
    stable) just looks at the bot's 8 neighbours and picks the one
    with the lowest `dist` — O(8) per step, independent of path
    length.

    Design trade-offs vs A*:
    - **No variable edge costs**: all walkable tiles cost 1 step.
      Transport preference, danger-zone avoidance, and other cost
      tricks that `AStarSearch` handled are NOT respected here.
      Walls and enemy buildings (cost_grid[i] >= INF) are the only
      impassable tiles. Caller is responsible for micro-avoiding
      turret firing lines at step time.
    - **Budget-gated + resumable**: BFS state (`_q`, `_qi`, `_qlen`,
      `_gen`) persists across turns. If CPU runs out mid-fill, next
      turn picks up where we left off. Complete fill of a 50x50
      map is ~2500 node expansions x ~8 neighbours = 20k ops;
      typically done in 1 turn on CPython, 1-2 turns worst-case.
    - **Generation counter trick**: `_gen[i] == _g` indicates "this
      tile has a valid dist for the current search". Avoids having
      to clear `_dist` on restart — we just bump `_g`.

    Same external interface as `AStarSearch`: `search`,
    `search_blocked`, `no_path`, for drop-in replacement in
    `move_search`.
    """

    def __init__(self) -> None:
        self._w = 0
        self._h = 0
        self._pw = 0
        self._pad = 0
        self._pn = 0
        # Padded flat-index offsets for 8 neighbours, computed at
        # _init_grid time once pw is known. Each entry is
        # (flat_offset, dx, dy) — we store dx/dy explicitly so
        # `_best_step` doesn't need to reverse-engineer them from
        # the flat offset (Python's divmod floor semantics make
        # that surprisingly error-prone for negative offsets).
        self._neighbor_offsets: list[tuple[int, int, int]] = []
        # Flat-only list for the BFS inner loop (hot path).
        self._neighbor_flat: list[int] = []
        # dist: steps from goal (BFS fills outward); gen: marks
        # which tiles have valid dist for the current search. BFS
        # "resets" by bumping _g instead of zeroing dist.
        self._dist: list[int] = []
        self._gen: bytearray = bytearray()
        self._g: int = 0
        # FIFO queue as a ring-style flat array.
        self._q: list[int] = []
        self._qi: int = 0
        self._qlen: int = 0
        # Previous goal index, used to detect target change.
        self._goal_idx: int = -1
        self._finished = True
        self._no_path = False
        self._prev_no_path = False
        self._running_target: Position | None = None
        self._prev_target: Position | None = None

    def _init_grid(self, state: State) -> None:
        self._w, self._h = state.w, state.h
        self._pw = state.pw
        self._pad = state.pad
        self._pn = state.pw * state.ph
        self._dist = [0] * self._pn
        self._gen = bytearray(self._pn)
        self._q = [0] * self._pn
        pw = self._pw
        self._neighbor_offsets = [
            (-pw - 1, -1, -1),
            (-pw, 0, -1),
            (-pw + 1, 1, -1),
            (-1, -1, 0),
            (1, 1, 0),
            (pw - 1, -1, 1),
            (pw, 0, 1),
            (pw + 1, 1, 1),
        ]
        self._neighbor_flat = [off for off, _, _ in self._neighbor_offsets]

    def _reset_for_goal(self, state: State, goal: Position) -> None:
        if self._pn != state.pw * state.ph:
            self._init_grid(state)
        # Bump generation counter. This invalidates all previous
        # dist values without needing to clear the array.
        self._g = (self._g + 1) & 0xFF
        if self._g == 0:
            # Wrap: actually clear gen so stale bytes don't alias.
            self._gen = bytearray(self._pn)
            self._g = 1
        pw = self._pw
        pad = self._pad
        gi = (goal.y + pad) * pw + (goal.x + pad)
        self._goal_idx = gi
        self._dist[gi] = 0
        self._gen[gi] = self._g
        self._q[0] = gi
        self._qi = 0
        self._qlen = 1
        self._no_path = False

    def _compute(
        self,
        state: State,
        ct: Controller,
        cur_idx: int,
    ) -> bool:
        """Run (or resume) BFS fill. Returns True if fully complete
        (queue empty or bot's tile reached), False if we bailed on
        CPU budget and want to resume next turn.

        Goal-directedness: `cur_idx` is the padded flat index of
        the bot asking for a path. BFS stops one level past the
        wave that contains the bot — we don't need to fill the
        rest of the map. This turns BFS back into a goal-directed
        search with node count comparable to A*, avoiding the
        "BFS spends 3 turns filling a huge maze before the bot
        has any dist info" failure mode on large maps.

        A tile is passable iff its `cost_grid` value is strictly
        below the launcher-penalty threshold (20): walls, enemy
        buildings, AND launcher-adjacent danger zones are all
        treated as hard-impassable so BFS never routes through
        them. In v54, `adjacent_to_enemy_launcher` tiles are
        cost_grid entries with +20 added — seen empty (3) + 20 =
        23, which exceeds our gate.
        """
        cost = state.cost_grid
        neighbor_flat = self._neighbor_flat
        dist = self._dist
        gen = self._gen
        g = self._g
        q = self._q
        qi = self._qi
        qlen = self._qlen
        # Stop as soon as we've processed the wave after the bot.
        # `stop_at` is the max depth we'll process; it starts
        # unbounded and gets clamped once we touch cur_idx.
        stop_at = dist[cur_idx] + 1 if gen[cur_idx] == g else _INF

        while qi < qlen:
            node = q[qi]
            qi += 1
            nd = dist[node] + 1
            if nd > stop_at:
                # We've already expanded one wave past the bot.
                # Reset qi so `resume` on next call can continue
                # if the bot moves further away.
                qi -= 1
                self._qi = qi
                self._qlen = qlen
                return True
            for off in neighbor_flat:
                ni = node + off
                if gen[ni] == g:
                    continue
                if cost[ni] >= 20:
                    continue
                gen[ni] = g
                dist[ni] = nd
                q[qlen] = ni
                qlen += 1
                if ni == cur_idx:
                    stop_at = nd + 1
            if qi & 255 == 0 and ct.get_cpu_time_elapsed() > _CPU_BUDGET:
                self._qi = qi
                self._qlen = qlen
                return False

        self._qi = qi
        self._qlen = qlen
        return True

    def _best_step(
        self, state: State, ct: Controller, start: Position
    ) -> Position | None:
        """Look at start's 8 neighbours and pick the best one.

        Selection criteria (in order):
        1. Lowest `dist` field (closest to goal).
        2. Tiebreak: prefer `cost_grid == 1` (existing friendly
           transport — walking onto it is FREE, whereas walking
           onto empty terrain triggers a road-build that costs Ti).
        3. Hard-skip: any neighbour inside an enemy turret's
           current attack pattern. The cost_grid already excludes
           launcher-adjacent zones via the `cost[ni] >= 20` gate
           in `_compute`, but gunners / sentinels / breach attack
           along forward rays that aren't captured in the static
           cost grid. We ask the controller per-step here.
        """
        pw = self._pw
        pad = self._pad
        dist = self._dist
        gen = self._gen
        g = self._g
        cost = state.cost_grid
        blocked = _turret_blocked_tiles(state, ct, start)
        ci = (start.y + pad) * pw + (start.x + pad)
        best_d = _INF
        best_tie = _INF
        best_dx = 0
        best_dy = 0
        for off, dx, dy in self._neighbor_offsets:
            ni = ci + off
            if gen[ni] != g:
                continue
            if cost[ni] >= 20:
                continue
            cand = Position(start.x + dx, start.y + dy)
            if cand in blocked:
                continue
            d = dist[ni]
            # Tie-break: prefer tiles with lower cost_grid value.
            # Existing transport = 1 (free step), empty = 3 (costs
            # a road build). So at same `d`, transport wins.
            tie = cost[ni]
            if d < best_d or (d == best_d and tie < best_tie):
                best_d = d
                best_tie = tie
                best_dx = dx
                best_dy = dy
        if best_d >= _INF:
            return None
        return Position(start.x + best_dx, start.y + best_dy)

    def search(
        self, state: State, ct: Controller, start: Position, target: Position
    ) -> list[Position] | None:
        """Return a 2-element `[start, next_step]` path toward target,
        or None if no path. Matches AStarSearch's external contract."""
        if self._pn != state.pw * state.ph:
            self._init_grid(state)
        pw = self._pw
        pad = self._pad
        goal_idx = (target.y + pad) * pw + (target.x + pad)
        cur_idx = (start.y + pad) * pw + (start.x + pad)
        if goal_idx != self._goal_idx:
            self._reset_for_goal(state, target)
        # Continue BFS fill until budget exhausted or the wave
        # containing the bot has been processed. Stopping early
        # keeps BFS goal-directed instead of filling the whole map.
        self._compute(state, ct, cur_idx)
        self._running_target = target
        self._prev_target = target
        next_step = self._best_step(state, ct, start)
        if next_step is None:
            # BFS hasn't reached us yet (or goal is unreachable).
            # Report no_path so callers fall through to fallback_nav.
            self._no_path = True
            self._prev_no_path = True
            return None
        self._no_path = False
        self._prev_no_path = False
        return [start, next_step]

    def search_blocked(
        self, state: State, ct: Controller, start: Position, goal: Position
    ) -> list[Position] | None:
        """Same as `search` but temporarily masks tiles occupied by
        other bots as impassable during the search."""
        cost = state.cost_grid
        pw = state.pw
        pad = state.pad
        saved: list[tuple[int, int]] = []
        for pos in ct.get_nearby_tiles(2):
            if ct.get_tile_builder_bot_id(pos) is not None and pos != start:
                idx = (pos.y + pad) * pw + (pos.x + pad)
                saved.append((idx, cost[idx]))
                cost[idx] = _INF
        # Temporarily blocked tiles: invalidate the distance field
        # since tiles may have flipped passability under our feet.
        self._goal_idx = -1
        result = self.search(state, ct, start, goal)
        for idx, val in saved:
            cost[idx] = val
        # Also invalidate so next search rebuilds without the blocks.
        self._goal_idx = -1
        return result

    @property
    def no_path(self) -> bool:
        return self._prev_no_path


class MoveHeapAstar:
    """Heap-based A* dedicated to builder-bot movement pathfinding.

    This is a slimmed-down port of v52_live's `AStarSearch`, adapted
    to read v54's PADDED `cost_grid` via `(y+pad)*pw + (x+pad)`.
    Kept deliberately separate from the bucket `AStarSearch` used
    for chain routing — that class has lots of per-search
    infrastructure (coord arrays, bridge neighbourhoods, bucket
    tuning) that movement doesn't need, and its initialisation cost
    makes the first turn of every bot slow on CPython.

    Movement paths want:
    - 8-direction neighbourhood (cardinal + diagonal, cost 0 extra)
    - Chebyshev heuristic (admissible + consistent for 8-connected)
    - Minimal per-search state (just `dist` + visited bitmap)
    - Simple heap priority queue (no bucket math, no relaxation)

    Same external interface as `AStarSearch`: `search`,
    `search_blocked`, `no_path`.
    """

    def __init__(self) -> None:
        self._w = 0
        self._h = 0
        self._pw = 0
        self._pad = 0
        self._dist: list[int] = []
        self._visited = bytearray()
        self._prev_visited = bytearray()
        self._q: list[tuple[float, int, Position]] = []
        self._finished = True
        self._no_path = False
        self._prev_no_path = False
        self._running_target: Position | None = None
        self._prev_target: Position | None = None

    def _init_grid(self, state: State) -> None:
        self._w, self._h = state.w, state.h
        self._pw = state.pw
        self._pad = state.pad
        pn = state.pw * state.ph
        self._dist = [_INF] * pn

    def _reset(self, state: State) -> None:
        pn = state.pw * state.ph
        if len(self._dist) != pn:
            self._init_grid(state)
        self._no_path = False
        self._visited = bytearray((pn + 7) // 8)
        self._q = []

    def _pidx(self, pos: Position) -> int:
        return (pos.y + self._pad) * self._pw + (pos.x + self._pad)

    def _extract_path(
        self, state: State, start: Position, target: Position
    ) -> list[Position]:
        cost = state.cost_grid
        pw = self._pw
        pad = self._pad
        path: list[Position] = []
        current = start
        while current != target:
            if current in path:
                break
            path.append(current)
            best_dist = _INF
            best = current
            ci = (current.y + pad) * pw + (current.x + pad)
            for dx, dy in _DIR8_DELTA:
                nx = current.x + dx
                ny = current.y + dy
                if not (0 <= nx < self._w and 0 <= ny < self._h):
                    continue
                idx = ci + dy * pw + dx
                if (self._prev_visited[idx >> 3] & (1 << (idx & 7))) and cost[
                    idx
                ] < _INF:
                    d = self._dist[idx]
                    if d < best_dist:
                        best_dist = d
                        best = Position(nx, ny)
            current = best
        path.append(target)
        return path

    def _run(
        self, state: State, ct: Controller, start: Position, goal: Position
    ) -> bool:
        cost = state.cost_grid
        pw = self._pw
        pad = self._pad
        w_bound = self._w
        h_bound = self._h
        dist = self._dist
        visited = self._visited
        q = self._q

        gi = (goal.y + pad) * pw + (goal.x + pad)
        dist[gi] = 0
        visited[gi >> 3] |= 1 << (gi & 7)
        # Tuple (f, counter, node_pos) — counter for stable ordering.
        counter = 0
        heapq.heappush(q, (0, counter, goal))
        counter += 1

        sx, sy = start.x, start.y
        while q:
            _, _, current = heapq.heappop(q)
            if current == start:
                return True
            if ct.get_cpu_time_elapsed() > _CPU_BUDGET:
                return False

            ci = (current.y + pad) * pw + (current.x + pad)
            cur_dist = dist[ci]
            for dx, dy in _DIR8_DELTA:
                nx = current.x + dx
                ny = current.y + dy
                if nx < 0 or nx >= w_bound or ny < 0 or ny >= h_bound:
                    continue
                idx = ci + dy * pw + dx
                if visited[idx >> 3] & (1 << (idx & 7)):
                    continue
                move_cost = cost[idx]
                if move_cost >= _INF:
                    continue
                visited[idx >> 3] |= 1 << (idx & 7)
                new_dist = cur_dist + move_cost
                dist[idx] = new_dist
                # Chebyshev heuristic (admissible for 8-connected).
                dxh = abs(nx - sx)
                dyh = abs(ny - sy)
                f = new_dist + (max(dyh, dxh))
                heapq.heappush(q, (f, counter, Position(nx, ny)))
                counter += 1

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
        cost = state.cost_grid
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


move_search = MoveHeapAstar()
# Empirically, allow_relaxation=True is load-bearing for path
# quality, not just bucket-overflow protection. Theory says Dial's
# bucket A* with a consistent heuristic shouldn't need it, but every
# relax-off sweep regressed to ~35-40% (vs 80% with relax on).
# Leaving it on.
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
