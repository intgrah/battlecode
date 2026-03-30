"""Benchmark pathfinding techniques in a realistic exploration simulation.

For each of 38 maps, a builder starts at CORE_A with blank belief, explores
toward CORE_B, discovering tiles each turn.  Measures per-turn time,
correctness, and optimality for multiple pathfinding approaches.

Usage:
    python -m scripts.bench_pathfinding_techniques
"""

import heapq
import math
import sys
import time
import types
from collections import deque
from pathlib import Path

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------
_cambc = types.ModuleType("cambc")


class _Env:
    EMPTY = 0
    WALL = 1
    ORE_TITANIUM = 2
    ORE_AXIONITE = 3


class _Pos:
    __slots__ = ("x", "y")

    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y

    def __eq__(self, o: object) -> bool:
        return isinstance(o, _Pos) and self.x == o.x and self.y == o.y

    def __hash__(self) -> int:
        return hash((self.x, self.y))


_cambc.Environment = _Env  # type: ignore[attr-defined]
_cambc.Position = _Pos  # type: ignore[attr-defined]
sys.modules["cambc"] = _cambc

_util = types.ModuleType("util")
_util.Symmetry = type(  # type: ignore[attr-defined]
    "SymEnum",
    (),
    {
        "ROT": type("S", (), {"name": "ROT"})(),
        "HOR": type("S", (), {"name": "HOR"})(),
        "VER": type("S", (), {"name": "VER"})(),
    },
)()
sys.modules["util"] = _util

_v50 = str(Path(__file__).resolve().parent.parent / "bots" / "intgrah" / "v50")
if _v50 not in sys.path:
    sys.path.insert(0, _v50)

from hardcode.known import KnownMap  # noqa: E402
from hardcode.map import CORE_A, CORE_B, DIMENSIONS, TILES, decode  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_INF = 1_000_000
_COST_ROAD = 2
_COST_EMPTY = 10
_COST_UNSEEN = 12
_DIR8 = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))
_VIS_RSQ = 20
_r = math.isqrt(_VIS_RSQ)
_VIS_OFFSETS = [
    (dx, dy)
    for dx in range(-_r, _r + 1)
    for dy in range(-_r, _r + 1)
    if dx * dx + dy * dy <= _VIS_RSQ
]


# ---------------------------------------------------------------------------
# Shared belief state
# ---------------------------------------------------------------------------


class Belief:
    __slots__ = ("cost", "env", "h", "n", "neighbors", "true_env", "w")

    def __init__(self, w: int, h: int, true_tiles: list[int]) -> None:
        self.w = w
        self.h = h
        self.n = w * h
        self.env: list[int | None] = [None] * self.n
        self.true_env: list[int] = true_tiles
        # Flat cost array: initially all unseen.
        self.cost: list[int] = [_COST_UNSEEN] * self.n
        # Precomputed neighbors: (neighbor_tile, is_diagonal)
        neighbors: list[list[tuple[int, bool]]] = [[] for _ in range(self.n)]
        for i in range(self.n):
            cx, cy = i % w, i // w
            for dx, dy in _DIR8:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h:
                    neighbors[i].append((ny * w + nx, dx != 0 and dy != 0))
        self.neighbors = neighbors

    def reveal(self, bx: int, by: int) -> list[tuple[int, bool]]:
        """Reveal tiles in vision. Returns (tile_index, is_wall) for changed tiles."""
        w, h = self.w, self.h
        changed: list[tuple[int, bool]] = []
        for dx, dy in _VIS_OFFSETS:
            x, y = bx + dx, by + dy
            if 0 <= x < w and 0 <= y < h:
                i = y * w + x
                if self.env[i] is None:
                    tv = self.true_env[i]
                    self.env[i] = tv
                    if tv == 1:  # wall
                        self.cost[i] = _INF
                    else:
                        self.cost[i] = _COST_EMPTY
                    changed.append((i, tv == 1))
        return changed

    def clone(self) -> "Belief":
        b = Belief.__new__(Belief)
        b.w = self.w
        b.h = self.h
        b.n = self.n
        b.env = list(self.env)
        b.true_env = self.true_env
        b.cost = list(self.cost)
        b.neighbors = self.neighbors  # shared, immutable
        return b


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------


def validate_path(
    belief: Belief, path: list[int], si: int, gi: int
) -> tuple[int, str | None]:
    w = belief.w
    cost = belief.cost
    if not path:
        return _INF, "empty"
    if path[0] != si:
        return _INF, "start"
    if path[-1] != gi:
        return _INF, "goal"
    total = 0
    for i in range(len(path) - 1):
        x0, y0 = path[i] % w, path[i] // w
        x1, y1 = path[i + 1] % w, path[i + 1] // w
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        if dx > 1 or dy > 1:
            return _INF, f"non-adj {i}"
        c = cost[path[i + 1]]
        if c >= _INF:
            return _INF, f"wall {i}"
        if dx != 0 and dy != 0:
            c += 1
        total += c
    return total, None


def ground_truth_dijkstra(belief: Belief, goal: int) -> list[int]:
    """Dijkstra from goal over belief state. Returns dist[tile]."""
    n = belief.n
    cost = belief.cost
    nb = belief.neighbors
    dist = [_INF] * n
    dist[goal] = 0
    heap: list[tuple[int, int]] = [(0, goal)]
    while heap:
        d, node = heapq.heappop(heap)
        if d > dist[node]:
            continue
        for ni, diag in nb[node]:
            c = cost[ni]
            if c >= _INF:
                continue
            if diag:
                c += 1
            nd = d + c
            if nd < dist[ni]:
                dist[ni] = nd
                heapq.heappush(heap, (nd, ni))
    return dist


# ---------------------------------------------------------------------------
# Technique 1: Baseline A* with Chebyshev (dict-based, like NavAstar)
# ---------------------------------------------------------------------------


def astar_baseline(belief: Belief, si: int, gi: int) -> list[int] | None:
    w = belief.w
    cost = belief.cost
    gx, gy = gi % w, gi // w
    if si == gi:
        return [si]
    g: dict[int, int] = {si: 0}
    parent: dict[int, int | None] = {si: None}
    h0 = max(abs(si % w - gx), abs(si // w - gy)) * _COST_ROAD
    heap: list[tuple[int, int, int]] = [(h0, 0, si)]
    while heap:
        f, _, node = heapq.heappop(heap)
        g_node = g.get(node, _INF)
        hv = max(abs(node % w - gx), abs(node // w - gy)) * _COST_ROAD
        if f > g_node + hv:
            continue
        if node == gi:
            path: list[int] = []
            cur: int | None = node
            while cur is not None:
                path.append(cur)
                cur = parent.get(cur)
            path.reverse()
            return path
        cx, cy = node % w, node // w
        for dx, dy in _DIR8:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < belief.h:
                ni = ny * w + nx
                c = cost[ni]
                if c >= _INF:
                    continue
                if dx != 0 and dy != 0:
                    c += 1
                nd = g_node + c
                if nd < g.get(ni, _INF):
                    g[ni] = nd
                    parent[ni] = node
                    h = max(abs(nx - gx), abs(ny - gy)) * _COST_ROAD
                    heapq.heappush(heap, (nd + h, h, ni))
    return None


# ---------------------------------------------------------------------------
# Technique 2: Flat-array A* with Chebyshev
# ---------------------------------------------------------------------------


class FlatAstar:
    __slots__ = ("_g", "_n", "_parent", "_touched")

    def __init__(self, n: int) -> None:
        self._n = n
        self._g = [_INF] * n
        self._parent = [-1] * n
        self._touched: list[int] = []

    def search(self, belief: Belief, si: int, gi: int) -> list[int] | None:
        w = belief.w
        cost = belief.cost
        gx, gy = gi % w, gi // w
        if si == gi:
            return [si]
        g = self._g
        parent = self._parent
        touched = self._touched
        g[si] = 0
        touched.append(si)
        h0 = max(abs(si % w - gx), abs(si // w - gy)) * _COST_ROAD
        heap: list[tuple[int, int]] = [(h0, si)]
        result: list[int] | None = None
        while heap:
            f, node = heapq.heappop(heap)
            if node == gi:
                path: list[int] = []
                cur = gi
                while cur != -1:
                    path.append(cur)
                    cur = parent[cur]
                path.reverse()
                result = path
                break
            if f > g[node] + max(abs(node % w - gx), abs(node // w - gy)) * _COST_ROAD:
                continue
            g_node = g[node]
            cx, cy = node % w, node // w
            for dx, dy in _DIR8:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < belief.h:
                    ni = ny * w + nx
                    c = cost[ni]
                    if c >= _INF:
                        continue
                    if dx != 0 and dy != 0:
                        c += 1
                    nd = g_node + c
                    if nd < g[ni]:
                        if g[ni] == _INF:
                            touched.append(ni)
                        g[ni] = nd
                        parent[ni] = node
                        h = max(abs(nx - gx), abs(ny - gy)) * _COST_ROAD
                        heapq.heappush(heap, (nd + h, ni))
        for ti in touched:
            g[ti] = _INF
            parent[ti] = -1
        touched.clear()
        return result


# ---------------------------------------------------------------------------
# Technique 3: Flat-array A* with precomputed neighbors
# ---------------------------------------------------------------------------


class FlatAstarPrecomp:
    __slots__ = ("_g", "_n", "_parent", "_touched")

    def __init__(self, n: int) -> None:
        self._n = n
        self._g = [_INF] * n
        self._parent = [-1] * n
        self._touched: list[int] = []

    def search(self, belief: Belief, si: int, gi: int) -> list[int] | None:
        w = belief.w
        cost = belief.cost
        nb = belief.neighbors
        gx, gy = gi % w, gi // w
        if si == gi:
            return [si]
        g = self._g
        parent = self._parent
        touched = self._touched
        g[si] = 0
        touched.append(si)
        h0 = max(abs(si % w - gx), abs(si // w - gy)) * _COST_ROAD
        heap: list[tuple[int, int]] = [(h0, si)]
        result: list[int] | None = None
        while heap:
            f, node = heapq.heappop(heap)
            if node == gi:
                path: list[int] = []
                cur = gi
                while cur != -1:
                    path.append(cur)
                    cur = parent[cur]
                path.reverse()
                result = path
                break
            if f > g[node] + max(abs(node % w - gx), abs(node // w - gy)) * _COST_ROAD:
                continue
            g_node = g[node]
            for ni, diag in nb[node]:
                c = cost[ni]
                if c >= _INF:
                    continue
                if diag:
                    c += 1
                nd = g_node + c
                if nd < g[ni]:
                    if g[ni] == _INF:
                        touched.append(ni)
                    g[ni] = nd
                    parent[ni] = node
                    nix = ni % w
                    niy = ni // w
                    h = max(abs(nix - gx), abs(niy - gy)) * _COST_ROAD
                    heapq.heappush(heap, (nd + h, ni))
        for ti in touched:
            g[ti] = _INF
            parent[ti] = -1
        touched.clear()
        return result


# ---------------------------------------------------------------------------
# Technique 4: Backward BFS heuristic + flat A*
# ---------------------------------------------------------------------------


class BackwardBfsAstar:
    __slots__ = ("_g", "_h_table", "_h_valid", "_n", "_parent", "_touched")

    def __init__(self, n: int) -> None:
        self._n = n
        self._g = [_INF] * n
        self._parent = [-1] * n
        self._touched: list[int] = []
        self._h_table = [_INF] * n
        self._h_valid = False

    def invalidate(self) -> None:
        self._h_valid = False

    def _build_h_table(self, belief: Belief, gi: int) -> None:
        """BFS from goal (unweighted Chebyshev). h(n) = bfs_dist * COST_ROAD."""
        n = belief.n
        cost = belief.cost
        nb = belief.neighbors
        h = self._h_table
        # Reset
        for i in range(n):
            h[i] = _INF
        h[gi] = 0
        q = deque([gi])
        while q:
            node = q.popleft()
            nd = h[node] + _COST_ROAD
            for ni, _ in nb[node]:
                if cost[ni] < _INF and h[ni] == _INF:
                    h[ni] = nd
                    q.append(ni)
        self._h_valid = True

    def search(
        self, belief: Belief, si: int, gi: int, walls_discovered: bool
    ) -> list[int] | None:
        if not self._h_valid or walls_discovered:
            self._build_h_table(belief, gi)
        cost = belief.cost
        nb = belief.neighbors
        h_table = self._h_table
        if si == gi:
            return [si]
        g = self._g
        parent = self._parent
        touched = self._touched
        g[si] = 0
        touched.append(si)
        heap: list[tuple[int, int]] = [(h_table[si], si)]
        result: list[int] | None = None
        while heap:
            f, node = heapq.heappop(heap)
            if node == gi:
                path: list[int] = []
                cur = gi
                while cur != -1:
                    path.append(cur)
                    cur = parent[cur]
                path.reverse()
                result = path
                break
            if f > g[node] + h_table[node]:
                continue
            g_node = g[node]
            for ni, diag in nb[node]:
                c = cost[ni]
                if c >= _INF:
                    continue
                if diag:
                    c += 1
                nd = g_node + c
                if nd < g[ni]:
                    if g[ni] == _INF:
                        touched.append(ni)
                    g[ni] = nd
                    parent[ni] = node
                    heapq.heappush(heap, (nd + h_table[ni], ni))
        for ti in touched:
            g[ti] = _INF
            parent[ti] = -1
        touched.clear()
        return result


# ---------------------------------------------------------------------------
# Technique 5: Backward Dijkstra heuristic + flat A*
# ---------------------------------------------------------------------------


class BackwardDijkstraAstar:
    __slots__ = ("_g", "_h_table", "_h_valid", "_n", "_parent", "_touched")

    def __init__(self, n: int) -> None:
        self._n = n
        self._g = [_INF] * n
        self._parent = [-1] * n
        self._touched: list[int] = []
        self._h_table = [_INF] * n
        self._h_valid = False

    def _build_h_table(self, belief: Belief, gi: int) -> None:
        """Dijkstra from goal. h(n) = exact dist to goal on belief."""
        n = belief.n
        cost = belief.cost
        nb = belief.neighbors
        h = self._h_table
        for i in range(n):
            h[i] = _INF
        h[gi] = 0
        heap: list[tuple[int, int]] = [(0, gi)]
        while heap:
            d, node = heapq.heappop(heap)
            if d > h[node]:
                continue
            for ni, diag in nb[node]:
                c = cost[ni]
                if c >= _INF:
                    continue
                if diag:
                    c += 1
                nd = d + c
                if nd < h[ni]:
                    h[ni] = nd
                    heapq.heappush(heap, (nd, ni))
        self._h_valid = True

    def search(
        self, belief: Belief, si: int, gi: int, walls_discovered: bool
    ) -> list[int] | None:
        if not self._h_valid or walls_discovered:
            self._build_h_table(belief, gi)
        cost = belief.cost
        nb = belief.neighbors
        h_table = self._h_table
        if si == gi:
            return [si]
        g = self._g
        parent = self._parent
        touched = self._touched
        g[si] = 0
        touched.append(si)
        heap: list[tuple[int, int]] = [(h_table[si], si)]
        result: list[int] | None = None
        while heap:
            f, node = heapq.heappop(heap)
            if node == gi:
                path: list[int] = []
                cur = gi
                while cur != -1:
                    path.append(cur)
                    cur = parent[cur]
                path.reverse()
                result = path
                break
            if f > g[node] + h_table[node]:
                continue
            g_node = g[node]
            for ni, diag in nb[node]:
                c = cost[ni]
                if c >= _INF:
                    continue
                if diag:
                    c += 1
                nd = g_node + c
                if nd < g[ni]:
                    if g[ni] == _INF:
                        touched.append(ni)
                    g[ni] = nd
                    parent[ni] = node
                    heapq.heappush(heap, (nd + h_table[ni], ni))
        for ti in touched:
            g[ti] = _INF
            parent[ti] = -1
        touched.clear()
        return result


# ---------------------------------------------------------------------------
# Technique 6: Backward Dijkstra only (no A*)
# ---------------------------------------------------------------------------


class BackwardDijkstraOnly:
    __slots__ = ("_dist", "_n", "_parent", "_valid")

    def __init__(self, n: int) -> None:
        self._n = n
        self._dist = [_INF] * n
        self._parent = [-1] * n
        self._valid = False

    def _compute(self, belief: Belief, gi: int) -> None:
        n = belief.n
        cost = belief.cost
        nb = belief.neighbors
        dist = self._dist
        parent = self._parent
        for i in range(n):
            dist[i] = _INF
            parent[i] = -1
        dist[gi] = 0
        heap: list[tuple[int, int]] = [(0, gi)]
        while heap:
            d, node = heapq.heappop(heap)
            if d > dist[node]:
                continue
            for ni, diag in nb[node]:
                c = cost[ni]
                if c >= _INF:
                    continue
                if diag:
                    c += 1
                nd = d + c
                if nd < dist[ni]:
                    dist[ni] = nd
                    parent[ni] = node
                    heapq.heappush(heap, (nd, ni))
        self._valid = True

    def search(
        self, belief: Belief, si: int, gi: int, walls_discovered: bool
    ) -> list[int] | None:
        if not self._valid or walls_discovered:
            self._compute(belief, gi)
        if self._dist[si] >= _INF:
            return None
        # Extract path by following gradient.
        dist = self._dist
        cost = belief.cost
        nb = belief.neighbors
        path = [si]
        visited: set[int] = {si}
        cur = si
        while cur != gi:
            best_ni = -1
            best_cost = _INF
            for ni, diag in nb[cur]:
                c = cost[ni]
                if c >= _INF:
                    continue
                if diag:
                    c += 1
                total = c + dist[ni]
                if total < best_cost and ni not in visited:
                    best_cost = total
                    best_ni = ni
            if best_ni == -1:
                return None
            visited.add(best_ni)
            path.append(best_ni)
            cur = best_ni
        return path


# ---------------------------------------------------------------------------
# Technique 7: Incremental backward Dijkstra (Ramalingam-Reps style)
# ---------------------------------------------------------------------------


class IncrementalDijkstra:
    __slots__ = ("_dist", "_n", "_nb", "_pred", "_valid")

    def __init__(self, n: int) -> None:
        self._n = n
        self._dist = [_INF] * n
        self._pred = [-1] * n
        self._valid = False
        self._nb: list[list[tuple[int, bool]]] = []

    def _full_compute(self, belief: Belief, gi: int) -> None:
        n = belief.n
        cost = belief.cost
        nb = belief.neighbors
        self._nb = nb
        dist = self._dist
        pred = self._pred
        for i in range(n):
            dist[i] = _INF
            pred[i] = -1
        dist[gi] = 0
        heap: list[tuple[int, int]] = [(0, gi)]
        while heap:
            d, node = heapq.heappop(heap)
            if d > dist[node]:
                continue
            for ni, diag in nb[node]:
                c = cost[ni]
                if c >= _INF:
                    continue
                if diag:
                    c += 1
                nd = d + c
                if nd < dist[ni]:
                    dist[ni] = nd
                    pred[ni] = node
                    heapq.heappush(heap, (nd, ni))
        self._valid = True

    def on_walls_discovered(
        self, belief: Belief, gi: int, wall_tiles: list[int]
    ) -> None:
        """Incrementally update after walls discovered."""
        if not self._valid:
            self._full_compute(belief, gi)
            return
        dist = self._dist
        pred = self._pred
        cost = belief.cost
        nb = belief.neighbors
        # Mark wall tiles as unreachable.
        affected: list[int] = []
        for wt in wall_tiles:
            if dist[wt] < _INF:
                dist[wt] = _INF
                pred[wt] = -1
                affected.append(wt)
        # Propagate: find all nodes whose shortest path went through a wall.
        stack = list(affected)
        while stack:
            v = stack.pop()
            for ni, _ in nb[v]:
                if pred[ni] == v and dist[ni] < _INF:
                    dist[ni] = _INF
                    pred[ni] = -1
                    affected.append(ni)
                    stack.append(ni)
        # Re-propagate from neighbors of affected nodes.
        heap: list[tuple[int, int]] = []
        for v in affected:
            for ni, diag in nb[v]:
                if dist[ni] < _INF:
                    heapq.heappush(heap, (dist[ni], ni))
        while heap:
            d, node = heapq.heappop(heap)
            if d > dist[node]:
                continue
            for ni, diag in nb[node]:
                c = cost[ni]
                if c >= _INF:
                    continue
                if diag:
                    c += 1
                nd = d + c
                if nd < dist[ni]:
                    dist[ni] = nd
                    pred[ni] = node
                    heapq.heappush(heap, (nd, ni))

    def search(
        self,
        belief: Belief,
        si: int,
        gi: int,
        wall_tiles: list[int],
    ) -> list[int] | None:
        if not self._valid:
            self._full_compute(belief, gi)
        elif wall_tiles:
            self.on_walls_discovered(belief, gi, wall_tiles)
        dist = self._dist
        cost = belief.cost
        nb = belief.neighbors
        if dist[si] >= _INF:
            return None
        path = [si]
        visited: set[int] = {si}
        cur = si
        while cur != gi:
            best_ni = -1
            best_cost = _INF
            for ni, diag in nb[cur]:
                c = cost[ni]
                if c >= _INF:
                    continue
                if diag:
                    c += 1
                total = c + dist[ni]
                if total < best_cost and ni not in visited:
                    best_cost = total
                    best_ni = ni
            if best_ni == -1:
                return None
            visited.add(best_ni)
            path.append(best_ni)
            cur = best_ni
        return path


# ---------------------------------------------------------------------------
# Technique 8: Bounded corridor A*
# ---------------------------------------------------------------------------


class BoundedAstar:
    __slots__ = ("_g", "_n", "_parent", "_touched")

    def __init__(self, n: int) -> None:
        self._n = n
        self._g = [_INF] * n
        self._parent = [-1] * n
        self._touched: list[int] = []

    def search(self, belief: Belief, si: int, gi: int) -> list[int] | None:
        w = belief.w
        cost = belief.cost
        nb = belief.neighbors
        gx, gy = gi % w, gi // w
        sx, sy = si % w, si // w
        if si == gi:
            return [si]
        # Corridor: Chebyshev distance from source-goal line, with margin.
        chebyshev_dist = max(abs(sx - gx), abs(sy - gy))
        margin = max(8, chebyshev_dist // 2)  # generous margin
        # Bounding box with margin.
        bx0 = max(0, min(sx, gx) - margin)
        by0 = max(0, min(sy, gy) - margin)
        bx1 = min(w, max(sx, gx) + margin + 1)
        by1 = min(belief.h, max(sy, gy) + margin + 1)

        g = self._g
        parent = self._parent
        touched = self._touched
        g[si] = 0
        touched.append(si)
        h0 = max(abs(sx - gx), abs(sy - gy)) * _COST_ROAD
        heap: list[tuple[int, int]] = [(h0, si)]
        result: list[int] | None = None
        while heap:
            f, node = heapq.heappop(heap)
            if node == gi:
                path: list[int] = []
                cur = gi
                while cur != -1:
                    path.append(cur)
                    cur = parent[cur]
                path.reverse()
                result = path
                break
            if f > g[node] + max(abs(node % w - gx), abs(node // w - gy)) * _COST_ROAD:
                continue
            g_node = g[node]
            for ni, diag in nb[node]:
                nix = ni % w
                niy = ni // w
                if nix < bx0 or nix >= bx1 or niy < by0 or niy >= by1:
                    continue
                c = cost[ni]
                if c >= _INF:
                    continue
                if diag:
                    c += 1
                nd = g_node + c
                if nd < g[ni]:
                    if g[ni] == _INF:
                        touched.append(ni)
                    g[ni] = nd
                    parent[ni] = node
                    h = max(abs(nix - gx), abs(niy - gy)) * _COST_ROAD
                    heapq.heappush(heap, (nd + h, ni))
        # Reset.
        for ti in touched:
            g[ti] = _INF
            parent[ti] = -1
        touched.clear()
        if result is not None:
            return result
        # Fallback: unbounded search.
        return FlatAstarPrecomp(self._n).search(belief, si, gi)


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------


def simulate_map(
    km: KnownMap,
) -> list[dict]:
    w, h = DIMENSIONS[km]
    n = w * h
    name = km.value

    env = decode(TILES[km](), n)
    true_tiles = [int(e) for e in env]
    ca, cb = CORE_A[km], CORE_B[km]
    gx, gy = cb.x, cb.y
    gi = gy * w + gx

    techniques: list[tuple[str, str]] = [
        ("baseline", "astar"),
        ("flat_array", "astar"),
        ("flat_precomp", "astar"),
        ("bfs_heuristic", "astar_h"),
        ("dijkstra_heuristic", "astar_h"),
        ("dijkstra_only", "dijkstra"),
        ("incremental_dijkstra", "incr"),
        ("bounded_astar", "astar"),
    ]

    results: list[dict] = []

    for tech_name, _tech_type in techniques:
        belief = Belief(w, h, true_tiles)
        bx, by = ca.x, ca.y
        si = by * w + bx

        # Init technique.
        if tech_name == "flat_array":
            searcher = FlatAstar(n)
        elif tech_name == "flat_precomp":
            searcher = FlatAstarPrecomp(n)
        elif tech_name == "bfs_heuristic":
            searcher = BackwardBfsAstar(n)
        elif tech_name == "dijkstra_heuristic":
            searcher = BackwardDijkstraAstar(n)
        elif tech_name == "dijkstra_only":
            searcher = BackwardDijkstraOnly(n)
        elif tech_name == "incremental_dijkstra":
            searcher = IncrementalDijkstra(n)
        elif tech_name == "bounded_astar":
            searcher = BoundedAstar(n)
        else:
            searcher = None

        turn_times: list[float] = []
        errors = 0
        arrived = False

        for turn in range(500):
            t0 = time.perf_counter()

            # 1. Reveal.
            changed = belief.reveal(bx, by)
            walls = [ti for ti, is_wall in changed if is_wall]
            any_walls = len(walls) > 0

            # 2. Search.
            si = by * w + bx
            if tech_name == "baseline":
                path = astar_baseline(belief, si, gi)
            elif tech_name in ("bfs_heuristic", "dijkstra_heuristic"):
                path = searcher.search(belief, si, gi, any_walls)
            elif tech_name == "incremental_dijkstra":
                # Also pass non-wall reveals that changed cost (unseen→empty).
                # Actually, unseen→empty changes cost from 12→10, which could
                # create shorter paths. Need to handle cost decreases too.
                # For simplicity, recompute on any change initially.
                [ti for ti, _ in changed]
                path = searcher.search(belief, si, gi, walls if any_walls else [])
            elif tech_name == "dijkstra_only":
                path = searcher.search(belief, si, gi, any_walls)
            elif tech_name == "bounded_astar":
                path = searcher.search(belief, si, gi)
            else:
                path = searcher.search(belief, si, gi)

            elapsed = (time.perf_counter() - t0) * 1e6
            turn_times.append(elapsed)

            # 3. Validate.
            if path is not None:
                _, err = validate_path(belief, path, si, gi)
                if err is not None:
                    errors += 1
                    if errors <= 3:
                        print(
                            f"  ERR {name}/{tech_name} turn {turn}: {err}",
                            file=sys.stderr,
                        )

            # 4. Move.
            if path is not None and len(path) >= 2:
                nxt = path[1]
                bx, by = nxt % w, nxt // w
                if bx == gx and by == gy:
                    arrived = True
                    # Record this last turn's time.
                    break

        s = sorted(turn_times)
        nt = len(s)
        results.append(
            {
                "map": name,
                "w": w,
                "h": h,
                "tech": tech_name,
                "turns": nt,
                "arrived": arrived,
                "errors": errors,
                "p50": round(s[nt // 2]),
                "p95": round(s[int(nt * 0.95)]),
                "p99": round(s[min(int(nt * 0.99), nt - 1)]),
                "max": round(s[-1]),
                "mean": round(sum(s) / nt),
            }
        )

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    header = (
        f"{'Map':<22} {'WxH':>5} "
        f"| {'Technique':<22} {'Trn':>4} {'OK':>3} {'Err':>4} "
        f"| {'p50':>7} {'p95':>7} {'p99':>7} {'max':>7} {'mean':>7}"
    )
    print(header)
    print("=" * len(header))

    all_results: list[dict] = []
    for km in KnownMap:
        print(f"  Running {km.value}...", file=sys.stderr, flush=True)
        results = simulate_map(km)
        all_results.extend(results)
        for r in results:
            ok = "Y" if r["arrived"] else "N"
            print(
                f"{r['map']:<22} {r['w']:>2}x{r['h']:<2} "
                f"| {r['tech']:<22} {r['turns']:>4} {ok:>3} {r['errors']:>4} "
                f"| {r['p50']:>6}u {r['p95']:>6}u {r['p99']:>6}u {r['max']:>6}u {r['mean']:>6}u"
            )

    # Aggregate summary.
    print("\n" + "=" * 100)
    print("AGGREGATE SUMMARY")
    print("=" * 100)
    tech_names = list(dict.fromkeys(r["tech"] for r in all_results))
    print(
        f"{'Technique':<22} "
        f"{'Arrive':>6} {'Err':>5} "
        f"{'p50':>7} {'p95':>7} {'p99':>7} {'max':>7} "
        f"{'>=2ms':>6} {'>=1ms':>6} {'>=500u':>6}"
    )
    print("-" * 100)
    for tech in tech_names:
        rows = [r for r in all_results if r["tech"] == tech]
        arrive = sum(1 for r in rows if r["arrived"])
        errs = sum(r["errors"] for r in rows)
        all_maxes = [r["max"] for r in rows]
        all_p50s = [r["p50"] for r in rows]
        all_p95s = [r["p95"] for r in rows]
        # Aggregate: median of per-map p50, max of per-map max, etc.
        all_maxes.sort()
        all_p50s.sort()
        all_p95s.sort()
        nm = len(rows)
        over_2ms = sum(1 for m in all_maxes if m > 2000)
        over_1ms = sum(1 for m in all_maxes if m > 1000)
        over_500 = sum(1 for m in all_maxes if m > 500)
        print(
            f"{tech:<22} "
            f"{arrive:>5}/{nm} {errs:>5} "
            f"{all_p50s[nm // 2]:>6}u {all_p95s[nm // 2]:>6}u {all_p95s[int(nm * 0.95)]:>6}u {max(all_maxes):>6}u "
            f"{over_2ms:>5}/{nm} {over_1ms:>5}/{nm} {over_500:>5}/{nm}"
        )


if __name__ == "__main__":
    main()
