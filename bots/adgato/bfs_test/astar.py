"""Anytime weighted A* pathfinding for builder bots.

Runs successive passes with decreasing heuristic weights (W=5 then W=2).
The first pass finds a suboptimal path quickly; later passes refine it.
"""

from __future__ import annotations

import heapq
from typing import TYPE_CHECKING

from cambc import Direction, EntityType, Environment, Position
from symmetry import Symmetry, mirror_idx

if TYPE_CHECKING:
    from collections.abc import Callable

INF = 1_000_000

COST_ROAD = 2
COST_EMPTY = 6
COST_UNSEEN = 6
COST_BUILDER = 1_000
COST_BUILT_IMPASSABLE = 10_000
COST_IMPASSABLE = INF

W_SCHEDULE: tuple[int, ...] = (5, 2)

DIR8_DELTA: tuple[tuple[int, int], ...] = tuple(
    d.delta()
    for d in (
        Direction.NORTH,
        Direction.EAST,
        Direction.SOUTH,
        Direction.WEST,
        Direction.NORTHEAST,
        Direction.SOUTHEAST,
        Direction.SOUTHWEST,
        Direction.NORTHWEST,
    )
)


_WALKABLE_BUILDINGS: frozenset[EntityType] = frozenset(
    {
        EntityType.ROAD,
        EntityType.CONVEYOR,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.SPLITTER,
        EntityType.BRIDGE,
    },
)


def _build_nb_chunk(
    nb: list[list[int]], w: int, h: int, start: int, within_budget: Callable[[], bool]
) -> int:
    """Compute neighbor table incrementally. Returns next index to resume from."""
    n = w * h
    for i in range(start, n):
        cx, cy = i % w, i // w
        for dx, dy in DIR8_DELTA:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                nb[i].append(ny * w + nx)
        if i & 15 == 0 and not within_budget():
            return i + 1
    return n


def _extract_path(p: list[int], si: int, gi: int) -> list[int]:
    """Extract path from parent array."""
    path = [gi]
    node = gi
    while node != si:
        node = p[node]
        if node == -1:
            return []
        path.append(node)
    path.reverse()
    return path


class NavAstar:
    """Anytime weighted A* navigation for builder bots.

    Uses flat arrays for g/parent, precomputed neighbor and heuristic tables.
    Maintains a persistent cost grid updated each round from vision.
    Runs successive passes with decreasing W to refine the path.
    """

    def __init__(self, w: int, h: int) -> None:
        self.w = w
        self.h = h
        self._n = w * h
        self._gx = 0
        self._gy = 0
        self._gi = 0
        self._si = 0
        self._cost_grid: list[int | None] = [None] * (w * h)
        self._nb: list[list[int]] = [[] for _ in range(w * h)]
        self._nb_progress = 0
        self._dirty = True
        self._searching = False
        self._path: list[int] | None = None
        self._path_idx = 0
        self._path_set: set[int] = set()

        # Anytime state
        self._w_idx = 0
        self._incumbent_cost = INF

        # A* state — flat arrays
        self._done = False
        self._result: list[int] | None = None
        self._g: list[int] = [INF] * (w * h)
        self._p: list[int] = [-1] * (w * h)
        self._touched: list[int] = []
        self._best_h = INF
        self._best_node = 0
        self._heap: list[tuple[int, int]] = []

    def update_tile(
        self,
        i: int,
        env: Environment,
        building_type: EntityType | None,
        is_allied_building: bool,
        is_builder: bool,
        sym: Symmetry = Symmetry.UNKNOWN,
    ) -> None:
        """Update a single tile's cost from raw tile data and check dirty flags."""
        # Compute cost
        if env == Environment.WALL:
            cost = COST_IMPASSABLE
        elif building_type is None:
            cost = COST_EMPTY
        elif building_type == EntityType.CORE:
            cost = COST_ROAD if is_allied_building else COST_IMPASSABLE
        elif building_type == EntityType.MARKER:
            cost = COST_EMPTY
        elif building_type in _WALKABLE_BUILDINGS:
            cost = COST_ROAD
        else:
            cost = COST_BUILT_IMPASSABLE
        # Builder bot overlay
        if is_builder and self._has_path and i == self._next_idx:
            cost = COST_BUILDER
            self._dirty = True
            self._has_path = False
        # Update grid and dirty check
        self._set_cost(i, cost)
        # Mirror environment via symmetry
        if sym is not Symmetry.UNKNOWN:
            mi = mirror_idx(i, sym, self.w, self.h)
            if self._cost_grid[mi] is None:
                env_cost = COST_IMPASSABLE if env == Environment.WALL else COST_EMPTY
                self._set_cost(mi, env_cost)

    def _set_cost(self, i: int, cost: int) -> None:
        """Write cost to grid and check dirty flags."""
        old_cost = self._cost_grid[i]
        if old_cost != cost:
            self._cost_grid[i] = cost
            if (
                self._has_path
                and cost > (old_cost or COST_UNSEEN)
                and i in self._path_set
            ):
                self._dirty = True
                self._has_path = False

    def mirror_known(self, sym: Symmetry, known_env: dict[int, Environment]) -> None:
        """Bulk-mirror all previously observed tile environments via symmetry."""
        w, h = self.w, self.h
        grid = self._cost_grid
        for i, env in known_env.items():
            mi = mirror_idx(i, sym, w, h)
            if grid[mi] is None:
                cost = COST_IMPASSABLE if env == Environment.WALL else COST_EMPTY
                grid[mi] = cost
        self._dirty = True

    def begin_update(self) -> None:
        """Prepare dirty-checking state before iterating tiles."""
        path = self._path
        self._has_path = path is not None and not self._dirty
        if self._has_path:
            pi = self._path_idx
            self._next_idx = path[pi + 1] if pi + 1 < len(path) else -1
        else:
            self._next_idx = -1

    def get_cost(self, pos: Position) -> int | None:
        """Return the cost grid value at a position, or None if unseen."""
        return self._cost_grid[pos.y * self.w + pos.x]

    def set_goal(self, goal: Position) -> None:
        """Change the goal. Marks dirty so the search resets."""
        if goal.x == self._gx and goal.y == self._gy:
            return
        self._gx = goal.x
        self._gy = goal.y
        self._gi = goal.y * self.w + goal.x
        self._dirty = True

    def _reset_search(self, source: int, w_heuristic: int) -> None:
        """Reset A* search state from a new source, keeping the cost grid."""
        # Clean up previous search
        g = self._g
        p = self._p
        for ti in self._touched:
            g[ti] = INF
            p[ti] = -1
        self._touched = [source]

        self._done = False
        self._result = None
        self._searching = True
        self._si = source
        self._best_h = INF
        self._best_node = source
        g[source] = 0
        sx, sy = source % self.w, source // self.w
        h0 = max(abs(sx - self._gx), abs(sy - self._gy)) * COST_ROAD * w_heuristic
        self._heap = [(h0, source)]

    def _compute(self, within_budget: Callable[[], bool], w_heuristic: int) -> None:
        """Run weighted A* within budget. Sets _done and _result when complete."""
        if self._done:
            return

        g = self._g
        p = self._p
        heap = self._heap
        gi = self._gi
        si = self._si
        gx = self._gx
        gy = self._gy
        w = self.w
        grid = self._cost_grid
        nb = self._nb
        touched = self._touched
        best_h = self._best_h
        best_node = self._best_node
        incumbent_cost = self._incumbent_cost
        _heappush = heapq.heappush
        _heappop = heapq.heappop
        _COST_UNSEEN = COST_UNSEEN
        _COST_ROAD = COST_ROAD
        _COST_IMPASSABLE = COST_IMPASSABLE
        _INF = INF
        _W = w_heuristic

        expanded = 0
        while heap:
            f, node = _heappop(heap)

            if node == gi:
                self._result = _extract_path(p, si, gi)
                self._done = True
                self._best_h = best_h
                self._best_node = best_node
                return

            ny = node // w
            node_h = max(abs(node - ny * w - gx), abs(ny - gy)) * _COST_ROAD
            if f > g[node] + node_h * _W:
                continue

            # Prune with incumbent solution cost
            if g[node] + node_h >= incumbent_cost:
                continue

            expanded += 1
            if expanded & 15 == 0 and not within_budget():
                break

            gn = g[node]
            for ni in nb[node]:
                c = grid[ni]
                wt = _COST_UNSEEN if c is None else c
                if wt >= _COST_IMPASSABLE:
                    continue
                nd = gn + wt
                if nd < g[ni]:
                    if g[ni] == _INF:
                        touched.append(ni)
                    g[ni] = nd
                    p[ni] = node
                    niy = ni // w
                    hval = max(abs(ni - niy * w - gx), abs(niy - gy)) * _COST_ROAD
                    # Prune: no point expanding if can't beat incumbent
                    if nd + hval >= incumbent_cost:
                        continue
                    _heappush(heap, (nd + hval * _W, ni))
                    if hval < best_h:
                        best_h = hval
                        best_node = ni

        self._best_h = best_h
        self._best_node = best_node

        if not heap:
            self._done = True

        if self._done and best_h < _INF:
            self._result = _extract_path(p, self._si, best_node)

    def _adopt_result(self) -> None:
        """Adopt the current search result as the incumbent path."""
        result = self._result
        if result is not None and len(result) >= 2:
            # Compute true path cost (sum of edge weights)
            grid = self._cost_grid
            cost = 0
            for idx in result[1:]:
                c = grid[idx]
                cost += COST_UNSEEN if c is None else c
            if cost < self._incumbent_cost:
                self._incumbent_cost = cost
                self._path = result
                self._path_idx = 1
                self._path_set = set(result)

    def _advance_pass(self, source: int) -> bool:
        """Start the next refinement pass. Returns False if schedule exhausted."""
        self._w_idx += 1
        if self._w_idx >= len(W_SCHEDULE):
            self._searching = False
            return False
        self._reset_search(source, W_SCHEDULE[self._w_idx])
        return True

    def step(
        self,
        pos: Position,
        within_budget: Callable[[], bool] = lambda: True,
    ) -> Position | None:
        """Advance one step. Returns the next Position to move to, or None if no path."""
        # Continue building neighbor table if not done
        if self._nb_progress < self._n:
            self._nb_progress = _build_nb_chunk(
                self._nb, self.w, self.h, self._nb_progress, within_budget
            )
            return None

        w = self.w
        cur_idx = pos.y * w + pos.x

        # If we have a cached path and it's not dirty, try to follow it
        if self._path is not None and not self._dirty:
            path = self._path
            idx = self._path_idx
            # Fast check: are we at the expected position?
            if idx < len(path) and path[idx] == cur_idx:
                next_step = self._follow_path(idx, cur_idx)
                if next_step is not None:
                    self._try_refine(cur_idx, within_budget)
                    return next_step
            # Slow fallback: search for our position
            elif cur_idx in self._path_set:
                new_idx = path.index(cur_idx)
                next_step = self._follow_path(new_idx, cur_idx)
                if next_step is not None:
                    self._try_refine(cur_idx, within_budget)
                    return next_step
            # Off the path — need to re-search
            self._dirty = True

        # Start or restart search if dirty
        if self._dirty:
            self._w_idx = 0
            self._incumbent_cost = INF
            self._reset_search(cur_idx, W_SCHEDULE[0])
            self._path = None
            self._path_idx = 0
            self._path_set = set()
            self._dirty = False

        # Continue incremental search
        if self._searching:
            self._compute(within_budget, W_SCHEDULE[self._w_idx])
            if self._done:
                self._adopt_result()
                self._advance_pass(cur_idx)
        # Return from incumbent if we have one
        if self._path is not None:
            return self._follow_path_unchecked()

        return None

    def _follow_path(self, idx: int, cur_idx: int) -> Position | None:
        """Follow the cached path from the given index. Returns next Position."""
        path = self._path
        assert path is not None
        if idx + 1 < len(path):
            self._path_idx = idx + 1
            self._path_set.discard(cur_idx)
            nxt = path[idx + 1]
            return Position(nxt % self.w, nxt // self.w)
        return None

    def _follow_path_unchecked(self) -> Position | None:
        """Return the next step from the incumbent path without position checks."""
        path = self._path
        if path is not None and self._path_idx < len(path):
            nxt = path[self._path_idx]
            return Position(nxt % self.w, nxt // self.w)
        return None

    def _try_refine(self, cur_idx: int, within_budget: Callable[[], bool]) -> None:
        """If still searching a refinement pass, spend remaining budget on it."""
        if not self._searching:
            return
        self._compute(within_budget, W_SCHEDULE[self._w_idx])
        if self._done:
            self._adopt_result()
            if not self._advance_pass(cur_idx):
                pass  # schedule exhausted

    def get_remaining_path(self) -> list[Position]:
        """Return remaining path as Positions."""
        if self._path is None:
            return []
        w = self.w
        return [Position(i % w, i // w) for i in self._path[self._path_idx :]]
