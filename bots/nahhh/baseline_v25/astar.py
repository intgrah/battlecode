"""A* pathfinding for walking and connect-back chain planning.

All coordinates are (x, y) int tuples internally — no Position objects
in the hot loop. Callers convert at boundaries.
"""

from __future__ import annotations

import heapq

# 8-directional deltas for walking
ALL_DELTAS = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))

# Cardinal-only deltas for conveyor chain routing
CARDINAL_DELTAS = ((0, -1), (1, 0), (0, 1), (-1, 0))

# Pre-computed bridge offsets: all (dx, dy) where dx²+dy² ≤ 9 and not (0,0)
BRIDGE_OFFSETS: list[tuple[int, int]] = [
    (dx, dy) for dx in range(-3, 4) for dy in range(-3, 4) if 0 < dx * dx + dy * dy <= 9
]


def astar_walk(
    sx: int,
    sy: int,
    gx: int,
    gy: int,
    wall_set: set,
    blocked_set: set,
    known_set: set,
    unit_positions: set,
    enemy_core_tiles: set,
    map_w: int,
    map_h: int,
    cpu_fn=None,
    cpu_limit: int = 1850,
    best_effort: bool = False,
) -> tuple[int, int] | None:
    """A* for unit movement. Returns (dx, dy) first step toward goal, or None.

    Cost model:
      1 — known passable tile
      2 — tile occupied by allied unit (temporary obstacle)
      3 — unseen tile (passable but penalized)
      inf — wall, blocked building, enemy core, out of bounds

    When best_effort=True and the goal is unreachable, returns the first step
    toward the closest reachable tile to the goal instead of None.
    """
    start = (sx, sy)
    goal = (gx, gy)
    if start == goal:
        return None

    # Pre-combine impassable for single lookup.
    impassable = wall_set | blocked_set | enemy_core_tiles

    _max = max
    _abs = abs
    _gx, _gy = gx, gy

    open_heap: list[tuple[int, int, int, int]] = []
    g_score: dict[tuple[int, int], int] = {start: 0}
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    counter = 0
    h0 = _max(_abs(sx - _gx), _abs(sy - _gy))
    heapq.heappush(open_heap, (h0, counter, sx, sy))
    counter += 1
    iterations = 0
    best_node: tuple[int, int] | None = None
    best_dist: int = h0 if best_effort else 0

    _heappush = heapq.heappush
    _heappop = heapq.heappop
    _g_get = g_score.get

    while open_heap:
        f, _, cx, cy = _heappop(open_heap)
        current = (cx, cy)

        if current == goal:
            node = goal
            while came_from.get(node) != start:
                parent = came_from.get(node)
                if parent is None:
                    return None
                node = parent
            return (node[0] - sx, node[1] - sy)

        current_g = _g_get(current, 999999)
        ch = _max(_abs(cx - _gx), _abs(cy - _gy))
        if f > current_g + ch:
            continue

        if best_effort and ch < best_dist:
            best_dist = ch
            best_node = current

        for dx, dy in ALL_DELTAS:
            nx, ny = cx + dx, cy + dy
            if nx < 0 or ny < 0 or nx >= map_w or ny >= map_h:
                continue
            nb = (nx, ny)
            if nb in impassable:
                continue

            if nb not in known_set:
                move_cost = 3
            elif nb in unit_positions:
                move_cost = 2
            else:
                move_cost = 1

            ng = current_g + move_cost
            if ng < _g_get(nb, 999999):
                g_score[nb] = ng
                came_from[nb] = current
                _heappush(
                    open_heap,
                    (ng + _max(_abs(nx - _gx), _abs(ny - _gy)), counter, nx, ny),
                )
                counter += 1

        iterations += 1
        if cpu_fn is not None and iterations % 20 == 0 and cpu_fn() > cpu_limit:
            if best_effort:
                break
            return None

    if best_effort and best_node is not None:
        node = best_node
        while came_from.get(node) != start:
            parent = came_from.get(node)
            if parent is None:
                return None
            node = parent
        return (node[0] - sx, node[1] - sy)
    return None


_EDGE_CONV = 0
_EDGE_BRIDGE = 1


def _reconstruct_chain(
    node: tuple[int, int],
    came_from: dict[tuple[int, int], tuple[int, int, int]],
    start: tuple[int, int],
) -> list[tuple[str, int, int, int, int]]:
    path: list[tuple[str, int, int, int, int]] = []
    while node in came_from:
        edge_type, px, py = came_from[node]
        if (px, py) == start:
            if edge_type == _EDGE_CONV:
                path.append(("conv", px, py, 0, 0))
            else:
                path.append(("bridge", px, py, node[0], node[1]))
            break
        if edge_type == _EDGE_CONV:
            path.append(("conv", px, py, 0, 0))
        else:
            path.append(("bridge", px, py, node[0], node[1]))
        node = (px, py)
    path.reverse()
    return path


def astar_chain(
    sx: int,
    sy: int,
    gx: int,
    gy: int,
    terminals: set,
    free_set: set,
    blocked_set: set,
    ore_set: set,
    wall_set: set,
    known_set: set,
    harvester_pos: tuple | None,
    map_w: int,
    map_h: int,
    cpu_fn=None,
    cpu_limit: int = 1850,
) -> list[tuple[str, int, int, int, int]] | None:
    """A* for connect-back chain planning.

    Returns a list of steps: [("conv", x, y, 0, 0), ("bridge", fx, fy, lx, ly), ...]
    Returns partial path toward goal if CPU exceeded. Returns None only if no progress.

    Cost model (int):
      conveyor on free tile: 1
      conveyor on unseen tile: 2
      conveyor on ore: 20
      bridge to known tile: 7
      bridge to unseen: 8
      bridge to ore: 20
    """
    start = (sx, sy)
    # Pre-combine impassable sets for single lookup.
    impassable = blocked_set | wall_set

    _abs = abs  # local ref for speed
    _gx, _gy = gx, gy

    open_heap: list[tuple[int, int, int, int]] = []
    g_score: dict[tuple[int, int], int] = {start: 0}
    came_from: dict[tuple[int, int], tuple[int, int, int]] = {}
    counter = 0
    h0 = _abs(sx - _gx) + _abs(sy - _gy)
    heapq.heappush(open_heap, (h0, counter, sx, sy))
    counter += 1
    iterations = 0

    best_h_node = start
    best_h_val = h0

    _heappush = heapq.heappush
    _heappop = heapq.heappop
    _g_get = g_score.get

    while open_heap:
        f, _, cx, cy = _heappop(open_heap)
        current = (cx, cy)

        if current != start and current in terminals:
            return _reconstruct_chain(current, came_from, start)

        current_g = _g_get(current, 999999)
        ch = _abs(cx - _gx) + _abs(cy - _gy)
        if f > current_g + ch:
            continue  # stale

        if ch < best_h_val and current != start:
            best_h_val = ch
            best_h_node = current

        # Conveyor edges: 4 cardinal neighbors
        for dx, dy in CARDINAL_DELTAS:
            nx, ny = cx + dx, cy + dy
            if nx < 0 or ny < 0 or nx >= map_w or ny >= map_h:
                continue
            nb = (nx, ny)
            if nb == harvester_pos:
                continue
            if nb in impassable and nb not in terminals:
                continue

            if nb in ore_set:
                cost = 20
            elif nb not in known_set:
                cost = 2
            else:
                cost = 1

            ng = current_g + cost
            if ng < _g_get(nb, 999999):
                g_score[nb] = ng
                came_from[nb] = (_EDGE_CONV, cx, cy)
                _heappush(
                    open_heap,
                    (ng + _abs(nx - _gx) + _abs(ny - _gy), counter, nx, ny),
                )
                counter += 1

        # Bridge edges: all tiles within dist_sq 9
        for bdx, bdy in BRIDGE_OFFSETS:
            lx, ly = cx + bdx, cy + bdy
            if lx < 0 or ly < 0 or lx >= map_w or ly >= map_h:
                continue
            lb = (lx, ly)
            if lb == harvester_pos:
                continue
            if lb in impassable and lb not in terminals:
                continue

            if lb in ore_set:
                cost = 20
            elif lb not in known_set:
                cost = 8
            else:
                cost = 7
            ng = current_g + cost
            if ng < _g_get(lb, 999999):
                g_score[lb] = ng
                came_from[lb] = (_EDGE_BRIDGE, cx, cy)
                _heappush(
                    open_heap,
                    (ng + _abs(lx - _gx) + _abs(ly - _gy), counter, lx, ly),
                )
                counter += 1

        iterations += 1
        if cpu_fn is not None and iterations % 20 == 0 and cpu_fn() > cpu_limit:
            if best_h_node != start:
                return _reconstruct_chain(best_h_node, came_from, start)
            return None

    return None
