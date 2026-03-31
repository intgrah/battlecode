"""Weighted A* (w=2) pathfinding for builder bots, based on bench_histograms.py."""

from __future__ import annotations

import heapq
from collections.abc import Callable

from cambc import Controller, Direction, EntityType, Environment, Position

INF = 1_000_000

COST_ROAD = 2
COST_EMPTY = 10
COST_UNSEEN = 12
COST_BUILDER = 1_000
COST_BUILT_IMPASSABLE = 10_000
COST_IMPASSABLE = INF

W_HEURISTIC = 2

DIR8_DELTA: tuple[tuple[int, int], ...] = tuple(
    d.delta()
    for d in (
        Direction.NORTH,
        Direction.NORTHEAST,
        Direction.EAST,
        Direction.SOUTHEAST,
        Direction.SOUTH,
        Direction.SOUTHWEST,
        Direction.WEST,
        Direction.NORTHWEST,
    )
)

# Buildings that are walkable (roads, conveyors, etc.)
_WALKABLE_BUILDINGS: frozenset[EntityType] = frozenset(
    {
        EntityType.ROAD,
        EntityType.CONVEYOR,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.SPLITTER,
        EntityType.BRIDGE,
    },
)


def _build_nb(w: int, h: int) -> list[list[tuple[int, bool]]]:
    """Precompute neighbor table: nb[i] = [(neighbor_idx, is_diagonal), ...]."""
    n = w * h
    nb: list[list[tuple[int, bool]]] = [[] for _ in range(n)]
    for i in range(n):
        cx, cy = i % w, i // w
        for dx, dy in DIR8_DELTA:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                nb[i].append((ny * w + nx, dx != 0 and dy != 0))
    return nb


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
    """Weighted A* (w=2) navigation for builder bots.

    Uses flat arrays for g/parent, precomputed neighbor and heuristic tables.
    Maintains a persistent cost grid updated each round from vision.
    Waits until search exhausts before following the path.
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
        self._nb = _build_nb(w, h)
        self._dirty = True
        self._searching = False
        self._path: list[int] | None = None
        self._path_idx = 0
        self._path_set: set[int] = set()

        # A* state — flat arrays
        self._done = False
        self._result: list[int] | None = None
        self._g: list[int] = [INF] * (w * h)
        self._p: list[int] = [-1] * (w * h)
        self._touched: list[int] = []
        self._best_h = INF
        self._best_node = 0
        self._heap: list[tuple[int, int]] = []

    def update(self, ct: Controller, pos: Position) -> None:
        """Update cost grid from current vision.
        Marks dirty if a terrain tile on the path got more expensive,
        or if a builder is blocking the next step."""
        w = self.w
        my_id = ct.get_id()
        my_team = ct.get_team()
        grid = self._cost_grid
        path = self._path
        dirty = self._dirty
        has_path = path is not None and not dirty
        # Next step: path_idx is where we are now, path_idx+1 is the next move
        if has_path:
            pi = self._path_idx
            next_idx = path[pi + 1] if pi + 1 < len(path) else -1
        else:
            next_idx = -1
        path_set = self._path_set
        for tile in ct.get_nearby_tiles():
            i = tile.y * w + tile.x
            # Terrain + buildings
            env = ct.get_tile_env(tile)
            if env == Environment.WALL:
                new_cost = COST_IMPASSABLE
            else:
                bid = ct.get_tile_building_id(tile)
                if bid is None:
                    new_cost = COST_EMPTY
                else:
                    etype = ct.get_entity_type(bid)
                    if etype == EntityType.CORE:
                        new_cost = COST_ROAD if ct.get_team(bid) == my_team else COST_IMPASSABLE
                    elif etype == EntityType.MARKER:
                        new_cost = COST_EMPTY
                    elif etype in _WALKABLE_BUILDINGS:
                        new_cost = COST_ROAD
                    else:
                        new_cost = COST_BUILT_IMPASSABLE
            # Builder bot overlay — always detect so cost grid is accurate
            bbid = ct.get_tile_builder_bot_id(tile)
            if bbid is not None and bbid != my_id:
                if has_path and i == next_idx:
                    new_cost = COST_BUILDER
                    dirty = True
                    has_path = False
            old_cost = grid[i]
            if old_cost != new_cost:
                grid[i] = new_cost
                if has_path and new_cost > (old_cost or COST_UNSEEN) and i in path_set:
                    dirty = True
                    has_path = False
        self._dirty = dirty

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

    def _reset_search(self, source: int) -> None:
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
        dx, dy = abs(sx - self._gx), abs(sy - self._gy)
        h0 = (max(dx, dy) * COST_ROAD + min(dx, dy)) * W_HEURISTIC
        self._heap = [(h0, source)]

    def _compute(self, within_budget: Callable[[], bool]) -> None:
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
        _heappush = heapq.heappush
        _heappop = heapq.heappop
        _COST_UNSEEN = COST_UNSEEN
        _COST_ROAD = COST_ROAD
        _COST_IMPASSABLE = COST_IMPASSABLE
        _INF = INF
        _W = W_HEURISTIC

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
            dx = abs(node - ny * w - gx)
            dy = abs(ny - gy)
            node_h = max(dx, dy) * _COST_ROAD + min(dx, dy)
            if f > g[node] + node_h * _W:
                continue

            expanded += 1
            if expanded & 15 == 0 and not within_budget():
                break

            gn = g[node]
            for ni, diag in nb[node]:
                c = grid[ni]
                wt = _COST_UNSEEN if c is None else c
                if wt >= _COST_IMPASSABLE:
                    continue
                if diag:
                    wt += 1
                nd = gn + wt
                if nd < g[ni]:
                    if g[ni] == _INF:
                        touched.append(ni)
                    g[ni] = nd
                    p[ni] = node
                    niy = ni // w
                    dx = abs(ni - niy * w - gx)
                    dy = abs(niy - gy)
                    hval = max(dx, dy) * _COST_ROAD + min(dx, dy)
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

    def step(self, pos: Position, within_budget: Callable[[], bool] = lambda: True) -> Position | None:
        """Advance one step. Returns the next Position to move to, or None if still searching."""
        w = self.w
        cur_idx = pos.y * w + pos.x

        # If we have a cached path, try to follow it
        if self._path is not None and not self._dirty:
            path = self._path
            idx = self._path_idx
            # Fast check: are we at the expected position?
            if idx < len(path) and path[idx] == cur_idx:
                if idx + 1 < len(path):
                    self._path_idx = idx + 1
                    self._path_set.discard(cur_idx)
                    nxt = path[idx + 1]
                    return Position(nxt % w, nxt // w)
            # Slow fallback: search for our position
            elif cur_idx in self._path_set:
                new_idx = path.index(cur_idx)
                if new_idx + 1 < len(path):
                    self._path_idx = new_idx + 1
                    self._path_set = set(path[new_idx + 1:])
                    nxt = path[new_idx + 1]
                    return Position(nxt % w, nxt // w)
            # Off the path — need to re-search
            self._dirty = True

        # Start or restart search if dirty
        if self._dirty:
            self._reset_search(cur_idx)
            self._path = None
            self._path_idx = 0
            self._path_set = set()
            self._dirty = False

        # Continue incremental search
        if self._searching:
            self._compute(within_budget)
            if self._done:
                self._searching = False
                if self._result is not None and len(self._result) >= 2:
                    self._path = self._result
                    self._path_idx = 1
                    self._path_set = set(self._result)
                    nxt = self._result[1]
                    return Position(nxt % w, nxt // w)

        return None

    def get_remaining_path(self) -> list[Position]:
        """Return remaining path as Positions."""
        if self._path is None:
            return []
        w = self.w
        return [Position(i % w, i // w) for i in self._path[self._path_idx:]]
