from __future__ import annotations

import heapq
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

_INF = 1_000_000
_DIR8 = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))


class GatewayGraph:
    __slots__ = (
        "_boundary_dirty",
        "_ch",
        "_cluster_gws",
        "_cost",
        "_cs",
        "_cw",
        "_dirty",
        "_fd_dist",
        "_fd_parent",
        "_fd_touched",
        "_free_gw",
        "_gateways",
        "_gw_adj",
        "_gw_cluster",
        "_gw_parent",
        "_gw_tile",
        "_h",
        "_n",
        "_neighbors",
        "_src_cache_ci",
        "_src_cache_dist",
        "_src_cache_parent",
        "_src_cache_tile",
        "_tile_cost",
        "_w",
    )

    def __init__(
        self,
        w: int,
        h: int,
        tile_cost: Callable[[int, int], int],
        cluster_size: int = 8,
    ) -> None:
        self._w = w
        self._h = h
        self._n = w * h
        self._cs = cluster_size
        self._cw = (w + cluster_size - 1) // cluster_size
        self._ch = (h + cluster_size - 1) // cluster_size
        self._tile_cost = tile_cost

        n = self._n
        cost = [0] * n
        for i in range(n):
            cost[i] = tile_cost(i % w, i // w)
        self._cost: list[int] = cost

        neighbors: list[list[tuple[int, bool]]] = [[] for _ in range(n)]
        for i in range(n):
            cx, cy = i % w, i // w
            for dx, dy in _DIR8:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h:
                    neighbors[i].append((ny * w + nx, dx != 0 and dy != 0))
        self._neighbors: list[list[tuple[int, bool]]] = neighbors

        self._gateways: list[tuple[int, int]] = []
        self._gw_tile: list[int] = []
        self._gw_cluster: list[tuple[int, int]] = []
        self._gw_adj: list[list[tuple[int, int]]] = []
        self._gw_parent: list[dict[int, int | None]] = []
        self._cluster_gws: list[list[int]] = [[] for _ in range(self._cw * self._ch)]
        self._free_gw: list[int] = []  # recycled gateway slot indices
        self._dirty: set[int] = set()
        self._boundary_dirty: bool = False

        self._src_cache_ci: int = -1
        self._src_cache_tile: int = -1
        self._src_cache_dist: dict[int, int] = {}
        self._src_cache_parent: dict[int, int | None] = {}

        self._fd_dist: list[int] = [_INF] * n
        self._fd_parent: list[int] = [-1] * n
        self._fd_touched: list[int] = []

        self._build_all()

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _cluster_of(self, x: int, y: int) -> int:
        return (y // self._cs) * self._cw + (x // self._cs)

    def _cluster_bounds(self, ci: int) -> tuple[int, int, int, int]:
        cs = self._cs
        cy, cx = divmod(ci, self._cw)
        x0 = cx * cs
        y0 = cy * cs
        x1 = min(x0 + cs, self._w)
        y1 = min(y0 + cs, self._h)
        return x0, y0, x1, y1

    def _is_passable(self, x: int, y: int) -> bool:
        return self._cost[y * self._w + x] < _INF

    def _cluster_neighbors(self, ci: int) -> list[int]:
        cw, ch = self._cw, self._ch
        cy, cx = divmod(ci, cw)
        result: list[int] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < cw and 0 <= ny < ch:
                    result.append(ny * cw + nx)
        return result

    def _is_on_boundary(self, x: int, y: int) -> bool:
        """True if tile (x,y) is on a cluster boundary edge."""
        cs = self._cs
        return x % cs == 0 or (x + 1) % cs == 0 or y % cs == 0 or (y + 1) % cs == 0

    # -----------------------------------------------------------------------
    # Full build
    # -----------------------------------------------------------------------

    def _build_all(self) -> None:
        self._gateways.clear()
        self._gw_tile.clear()
        self._gw_cluster.clear()
        self._gw_adj.clear()
        self._gw_parent.clear()
        for cg in self._cluster_gws:
            cg.clear()
        self._free_gw.clear()
        self._src_cache_ci = -1
        self._src_cache_tile = -1

        self._find_gateways()
        self._compute_intra_edges()

    def _alloc_gw_slot(self) -> int:
        """Get a gateway slot index, reusing freed slots or appending."""
        if self._free_gw:
            gi = self._free_gw.pop()
            self._gw_adj[gi] = []
            self._gw_parent[gi] = {}
            return gi
        gi = len(self._gw_tile)
        self._gw_tile.append(0)
        self._gw_cluster.append((0, 0))
        self._gw_adj.append([])
        self._gw_parent.append({})
        return gi

    def _add_gateway(self, x0: int, y0: int, x1: int, y1: int) -> None:
        w = self._w
        cost = self._cost
        ci_a = self._cluster_of(x0, y0)
        ci_b = self._cluster_of(x1, y1)
        t0 = y0 * w + x0
        t1 = y1 * w + x1
        gi_a = self._alloc_gw_slot()
        self._gw_tile[gi_a] = t0
        self._gw_cluster[gi_a] = (ci_a, ci_b)
        self._cluster_gws[ci_a].append(gi_a)
        gi_b = self._alloc_gw_slot()
        self._gw_tile[gi_b] = t1
        self._gw_cluster[gi_b] = (ci_b, ci_a)
        self._cluster_gws[ci_b].append(gi_b)
        c = cost[t1]
        if c >= _INF:
            c = _INF
        elif x0 != x1 and y0 != y1:
            c += 1
        self._gw_adj[gi_a].append((gi_b, c))
        self._gw_adj[gi_b].append((gi_a, c))
        self._gateways.append((gi_a, gi_b))

    def _find_gateways(self) -> None:
        w, h, cs, cw = self._w, self._h, self._cs, self._cw
        for cy in range(self._ch):
            for cx in range(self._cw):
                x0 = cx * cs
                y0 = cy * cs
                x1 = min(x0 + cs, w)
                y1 = min(y0 + cs, h)
                if cx + 1 < cw:
                    bx = x1
                    if bx < w:
                        self._scan_boundary_v(bx - 1, bx, y0, y1)
                if cy + 1 < self._ch:
                    by = y1
                    if by < h:
                        self._scan_boundary_h(x0, x1, by - 1, by)
                if cx + 1 < cw:
                    bx = x1
                    if bx < w:
                        self._scan_diagonal_v(bx - 1, bx, y0, y1)
                if cy + 1 < self._ch:
                    by = y1
                    if by < h:
                        self._scan_diagonal_h(x0, x1, by - 1, by)

    def _scan_diagonal_v(self, xa: int, xb: int, y0: int, y1: int) -> None:
        p = self._is_passable
        for y in range(y0, y1 - 1):
            if p(xa, y) and p(xb, y + 1) and not p(xa, y + 1) and not p(xb, y):
                self._add_gateway(xa, y, xb, y + 1)
            if p(xb, y) and p(xa, y + 1) and not p(xb, y + 1) and not p(xa, y):
                self._add_gateway(xb, y, xa, y + 1)

    def _scan_diagonal_h(self, x0: int, x1: int, ya: int, yb: int) -> None:
        p = self._is_passable
        for x in range(x0, x1 - 1):
            if p(x, ya) and p(x + 1, yb) and not p(x + 1, ya) and not p(x, yb):
                self._add_gateway(x, ya, x + 1, yb)
            if p(x + 1, ya) and p(x, yb) and not p(x, ya) and not p(x + 1, yb):
                self._add_gateway(x + 1, ya, x, yb)

    def _scan_boundary_v(self, xa: int, xb: int, y0: int, y1: int) -> None:
        run_start = -1
        for y in range(y0, y1):
            if self._is_passable(xa, y) and self._is_passable(xb, y):
                if run_start < 0:
                    run_start = y
            elif run_start >= 0:
                self._emit_gateways_v(xa, xb, run_start, y)
                run_start = -1
        if run_start >= 0:
            self._emit_gateways_v(xa, xb, run_start, y1)

    def _scan_boundary_h(self, x0: int, x1: int, ya: int, yb: int) -> None:
        run_start = -1
        for x in range(x0, x1):
            if self._is_passable(x, ya) and self._is_passable(x, yb):
                if run_start < 0:
                    run_start = x
            elif run_start >= 0:
                self._emit_gateways_h(ya, yb, run_start, x)
                run_start = -1
        if run_start >= 0:
            self._emit_gateways_h(ya, yb, run_start, x1)

    def _emit_gateways_v(self, xa: int, xb: int, y_start: int, y_end: int) -> None:
        length = y_end - y_start
        if length <= 3:
            mid = y_start + length // 2
            self._add_gateway(xa, mid, xb, mid)
        else:
            self._add_gateway(xa, y_start, xb, y_start)
            self._add_gateway(xa, y_end - 1, xb, y_end - 1)

    def _emit_gateways_h(self, ya: int, yb: int, x_start: int, x_end: int) -> None:
        length = x_end - x_start
        if length <= 3:
            mid = x_start + length // 2
            self._add_gateway(mid, ya, mid, yb)
        else:
            self._add_gateway(x_start, ya, x_start, yb)
            self._add_gateway(x_end - 1, ya, x_end - 1, yb)

    # -----------------------------------------------------------------------
    # Intra-cluster edges
    # -----------------------------------------------------------------------

    def _compute_intra_edges(self) -> None:
        for ci in range(self._cw * self._ch):
            self._compute_cluster_edges(ci)

    def _compute_cluster_edges(self, ci: int) -> None:
        gws = self._cluster_gws[ci]
        if len(gws) < 2:
            return
        x0, y0, x1, y1 = self._cluster_bounds(ci)
        for i, gi in enumerate(gws):
            dist, parent = self._cluster_dijkstra(self._gw_tile[gi], x0, y0, x1, y1)
            self._gw_parent[gi] = parent
            for gj in gws[i + 1 :]:
                tj = self._gw_tile[gj]
                d = dist.get(tj, _INF)
                if d < _INF:
                    self._gw_adj[gi].append((gj, d))
                    self._gw_adj[gj].append((gi, d))

    def _recompute_cluster_edges(self, ci: int) -> None:
        """Recompute intra-edges for a single cluster, clearing old ones first."""
        gws = self._cluster_gws[ci]
        # Clear intra-edges (edges where both endpoints are in this cluster).
        gws_set = set(gws)
        for gi in gws:
            self._gw_adj[gi] = [
                (nb, c) for nb, c in self._gw_adj[gi] if nb not in gws_set
            ]
            self._gw_parent[gi] = {}
        # Recompute.
        if len(gws) < 2:
            return
        x0, y0, x1, y1 = self._cluster_bounds(ci)
        for i, gi in enumerate(gws):
            dist, parent = self._cluster_dijkstra(self._gw_tile[gi], x0, y0, x1, y1)
            self._gw_parent[gi] = parent
            for gj in gws[i + 1 :]:
                tj = self._gw_tile[gj]
                d = dist.get(tj, _INF)
                if d < _INF:
                    self._gw_adj[gi].append((gj, d))
                    self._gw_adj[gj].append((gi, d))

    def _cluster_dijkstra(
        self, start: int, x0: int, y0: int, x1: int, y1: int
    ) -> tuple[dict[int, int], dict[int, int | None]]:
        w = self._w
        cost = self._cost
        dist: dict[int, int] = {start: 0}
        parent: dict[int, int | None] = {start: None}
        heap: list[tuple[int, int]] = [(0, start)]
        while heap:
            d, node = heapq.heappop(heap)
            if d > dist.get(node, _INF):
                continue
            nx_base, ny_base = node % w, node // w
            for dx, dy in _DIR8:
                nx, ny = nx_base + dx, ny_base + dy
                if nx < x0 or nx >= x1 or ny < y0 or ny >= y1:
                    continue
                ni = ny * w + nx
                c = cost[ni]
                if c >= _INF:
                    continue
                if dx != 0 and dy != 0:
                    c += 1
                nd = d + c
                if nd < dist.get(ni, _INF):
                    dist[ni] = nd
                    parent[ni] = node
                    heapq.heappush(heap, (nd, ni))
        return dist, parent

    # -----------------------------------------------------------------------
    # Fast Dijkstra (reusable flat arrays, for query-time local search)
    # -----------------------------------------------------------------------

    def _fast_dijkstra(
        self, start: int, goal: int, x0: int, y0: int, x1: int, y1: int
    ) -> list[int] | None:
        w = self._w
        cost = self._cost
        neighbors = self._neighbors
        dist = self._fd_dist
        parent = self._fd_parent
        touched = self._fd_touched
        dist[start] = 0
        touched.append(start)
        heap: list[tuple[int, int]] = [(0, start)]
        result: list[int] | None = None
        while heap:
            d, node = heapq.heappop(heap)
            if node == goal:
                path: list[int] = []
                cur = goal
                while cur != -1:
                    path.append(cur)
                    cur = parent[cur]
                path.reverse()
                result = path
                break
            if d > dist[node]:
                continue
            for ni, diag in neighbors[node]:
                ny = ni // w
                nx = ni - ny * w
                if nx < x0 or nx >= x1 or ny < y0 or ny >= y1:
                    continue
                c = cost[ni]
                if c >= _INF:
                    continue
                if diag:
                    c += 1
                nd = d + c
                if nd < dist[ni]:
                    if dist[ni] == _INF:
                        touched.append(ni)
                    dist[ni] = nd
                    parent[ni] = node
                    heapq.heappush(heap, (nd, ni))
        for ti in touched:
            dist[ti] = _INF
            parent[ti] = -1
        touched.clear()
        return result

    # -----------------------------------------------------------------------
    # Incremental rebuild
    # -----------------------------------------------------------------------

    def invalidate_tile(
        self, x: int, y: int, passability_changed: bool = False
    ) -> None:
        """Mark tile as changed.  Set passability_changed=True if the tile
        went from passable to impassable or vice versa (not just cost change)."""
        ci = self._cluster_of(x, y)
        self._dirty.add(ci)
        if passability_changed and self._is_on_boundary(x, y):
            self._boundary_dirty = True
        cs = self._cs
        if x % cs == 0 and x > 0:
            self._dirty.add(self._cluster_of(x - 1, y))
        if (x + 1) % cs == 0 and x + 1 < self._w:
            self._dirty.add(self._cluster_of(x + 1, y))
        if y % cs == 0 and y > 0:
            self._dirty.add(self._cluster_of(x, y - 1))
        if (y + 1) % cs == 0 and y + 1 < self._h:
            self._dirty.add(self._cluster_of(x, y + 1))

    def rebuild_dirty(self, tile_cost: Callable[[int, int], int]) -> None:
        if not self._dirty:
            return
        dirty = self._dirty
        self._tile_cost = tile_cost

        # 1. Refresh flat cost array for dirty clusters only.
        w = self._w
        cost = self._cost
        for ci in dirty:
            x0, y0, x1, y1 = self._cluster_bounds(ci)
            for yy in range(y0, y1):
                base = yy * w
                for xx in range(x0, x1):
                    cost[base + xx] = tile_cost(xx, yy)

        if self._boundary_dirty:
            # Gateway positions may have changed on boundaries involving
            # dirty clusters.  Surgically remove affected gateways and
            # re-scan only those boundaries, keeping stable indices.
            affected: set[int] = set(dirty)
            for ci in dirty:
                for ni in self._cluster_neighbors(ci):
                    affected.add(ni)

            # Kill gateways owned by affected clusters, recycle their slots.
            dead_gws: set[int] = set()
            for ci in affected:
                for gi in self._cluster_gws[ci]:
                    dead_gws.add(gi)
                    self._free_gw.append(gi)
                self._cluster_gws[ci] = []

            self._gateways = [(a, b) for a, b in self._gateways if a not in dead_gws]

            # Purge edges from clean gateways that pointed to dead ones.
            for gi in range(len(self._gw_adj)):
                if gi not in dead_gws and self._gw_adj[gi]:
                    self._gw_adj[gi] = [
                        (nb, c) for nb, c in self._gw_adj[gi] if nb not in dead_gws
                    ]

            # Re-scan boundaries for affected clusters (adds new gateways
            # that reuse the freed slots, keeping indices stable for
            # non-affected clusters).
            cs, cw, ch = self._cs, self._cw, self._ch
            scanned: set[tuple[int, int]] = set()
            for ci in affected:
                cy_c, cx_c = divmod(ci, cw)
                x0 = cx_c * cs
                y0 = cy_c * cs
                x1 = min(x0 + cs, self._w)
                y1 = min(y0 + cs, self._h)

                if cx_c + 1 < cw:
                    right = cy_c * cw + (cx_c + 1)
                    key = (min(ci, right), max(ci, right))
                    if key not in scanned:
                        scanned.add(key)
                        bx = x1
                        if bx < self._w:
                            self._scan_boundary_v(bx - 1, bx, y0, y1)
                            self._scan_diagonal_v(bx - 1, bx, y0, y1)

                if cx_c > 0:
                    left = cy_c * cw + (cx_c - 1)
                    key = (min(ci, left), max(ci, left))
                    if key not in scanned:
                        scanned.add(key)
                        bx = x0
                        ly0 = cy_c * cs
                        ly1 = min(ly0 + cs, self._h)
                        self._scan_boundary_v(bx - 1, bx, ly0, ly1)
                        self._scan_diagonal_v(bx - 1, bx, ly0, ly1)

                if cy_c + 1 < ch:
                    below = (cy_c + 1) * cw + cx_c
                    key = (min(ci, below), max(ci, below))
                    if key not in scanned:
                        scanned.add(key)
                        by = y1
                        if by < self._h:
                            self._scan_boundary_h(x0, x1, by - 1, by)
                            self._scan_diagonal_h(x0, x1, by - 1, by)

                if cy_c > 0:
                    above = (cy_c - 1) * cw + cx_c
                    key = (min(ci, above), max(ci, above))
                    if key not in scanned:
                        scanned.add(key)
                        by = y0
                        self._scan_boundary_h(x0, x1, by - 1, by)
                        self._scan_diagonal_h(x0, x1, by - 1, by)

            # Recompute intra-edges for all clusters that had gateways
            # added or removed.  This includes affected clusters and any
            # non-affected clusters that border affected clusters (they
            # received new boundary gateways from the re-scan).
            recompute: set[int] = set(affected)
            for ci in affected:
                for ni in self._cluster_neighbors(ci):
                    if ni not in affected and self._cluster_gws[ni]:
                        recompute.add(ni)
            for ci in recompute:
                self._recompute_cluster_edges(ci)
        else:
            # Only interior tiles changed — gateway positions are stable.
            # Just recompute intra-cluster edge weights for dirty clusters.
            for ci in dirty:
                self._recompute_cluster_edges(ci)

        self._src_cache_ci = -1
        self._src_cache_tile = -1
        self._boundary_dirty = False
        dirty.clear()

    # -----------------------------------------------------------------------
    # Path finding
    # -----------------------------------------------------------------------

    def find_path(self, sx: int, sy: int, gx: int, gy: int) -> list[int] | None:
        w = self._w
        si = sy * w + sx
        gi = gy * w + gx
        if si == gi:
            return [si]

        sci = self._cluster_of(sx, sy)
        gci = self._cluster_of(gx, gy)

        if sci == gci:
            x0, y0, x1, y1 = self._cluster_bounds(sci)
            result = self._fast_dijkstra(si, gi, x0, y0, x1, y1)
            if result is not None:
                return result

        scx, scy = divmod(sci, self._cw)
        gcx, gcy = divmod(gci, self._cw)
        if abs(scy - gcy) <= 1 and abs(scx - gcx) <= 1:
            sx0, sy0, sx1, sy1 = self._cluster_bounds(sci)
            gx0, gy0, gx1, gy1 = self._cluster_bounds(gci)
            lx0 = min(sx0, gx0)
            ly0 = min(sy0, gy0)
            lx1 = max(sx1, gx1)
            ly1 = max(sy1, gy1)
            local = self._fast_dijkstra(si, gi, lx0, ly0, lx1, ly1)
            if local is not None:
                return local

        src_dist, src_parent = self._get_src_temp(si, sci)
        dst_dist, dst_parent = self._insert_temp(gi, gci)

        if not src_dist or not dst_dist:
            return None

        n_gw = len(self._gw_tile)
        src_node = n_gw
        dst_node = n_gw + 1

        g: dict[int, int] = {src_node: 0}
        ab_parent: dict[int, int | None] = {src_node: None}
        heap: list[tuple[int, int, int]] = []
        gx_f, gy_f = gx, gy
        gw_tile = self._gw_tile
        gw_adj = self._gw_adj

        for gi_idx, c in src_dist.items():
            g[gi_idx] = c
            ab_parent[gi_idx] = src_node
            ti = gw_tile[gi_idx]
            tx = ti % w
            ty = ti // w
            h = max(abs(tx - gx_f), abs(ty - gy_f)) * 2
            heapq.heappush(heap, (c + h, gi_idx, c))

        best_total = _INF
        while heap:
            f_val, node, d = heapq.heappop(heap)
            if f_val >= best_total:
                break
            if d > g.get(node, _INF):
                continue
            if node in dst_dist:
                total = d + dst_dist[node]
                if total < best_total:
                    best_total = total
                    g[dst_node] = total
                    ab_parent[dst_node] = node
            for nb, ec in gw_adj[node]:
                nd = d + ec
                if nd < g.get(nb, _INF):
                    g[nb] = nd
                    ab_parent[nb] = node
                    ti = gw_tile[nb]
                    tx = ti % w
                    ty = ti // w
                    h = max(abs(tx - gx_f), abs(ty - gy_f)) * 2
                    heapq.heappush(heap, (nd + h, nb, nd))

        if dst_node not in ab_parent:
            return None

        abstract_path: list[int] = []
        cur: int | None = dst_node
        while cur is not None:
            abstract_path.append(cur)
            cur = ab_parent.get(cur)
        abstract_path.reverse()

        return self._refine_path(abstract_path, si, gi, src_parent, dst_parent)

    def _get_src_temp(
        self, tile: int, ci: int
    ) -> tuple[dict[int, int], dict[int, int | None]]:
        if ci == self._src_cache_ci and tile == self._src_cache_tile:
            dist = self._src_cache_dist
            parent = self._src_cache_parent
        else:
            x0, y0, x1, y1 = self._cluster_bounds(ci)
            dist, parent = self._cluster_dijkstra(tile, x0, y0, x1, y1)
            self._src_cache_ci = ci
            self._src_cache_tile = tile
            self._src_cache_dist = dist
            self._src_cache_parent = parent
        gw_dist: dict[int, int] = {}
        for gi in self._cluster_gws[ci]:
            t = self._gw_tile[gi]
            if t in dist:
                gw_dist[gi] = dist[t]
        return gw_dist, parent

    def _insert_temp(
        self, tile: int, ci: int
    ) -> tuple[dict[int, int], dict[int, int | None]]:
        x0, y0, x1, y1 = self._cluster_bounds(ci)
        dist, parent = self._cluster_dijkstra(tile, x0, y0, x1, y1)
        gw_dist: dict[int, int] = {}
        for gi in self._cluster_gws[ci]:
            t = self._gw_tile[gi]
            if t in dist:
                gw_dist[gi] = dist[t]
        return gw_dist, parent

    def _refine_path(
        self,
        abstract_path: list[int],
        si: int,
        gi: int,
        src_parent: dict[int, int | None],
        dst_parent: dict[int, int | None],
    ) -> list[int]:
        n_gw = len(self._gw_tile)
        src_node = n_gw
        dst_node = n_gw + 1
        tiles: list[int] = [si]

        for k in range(len(abstract_path) - 1):
            a = abstract_path[k]
            b = abstract_path[k + 1]

            if a == src_node:
                if b == dst_node:
                    seg = _extract(src_parent, gi)
                    _append_seg(tiles, seg)
                else:
                    seg = _extract(src_parent, self._gw_tile[b])
                    _append_seg(tiles, seg)
            elif b == dst_node:
                a_tile = self._gw_tile[a]
                seg = _extract(dst_parent, a_tile)
                if len(seg) >= 2:
                    seg.reverse()
                    _append_seg(tiles, seg)
                _append_seg(tiles, [gi])
            else:
                a_tile = self._gw_tile[a]
                b_tile = self._gw_tile[b]
                if a_tile == b_tile:
                    continue
                a_ci = self._cluster_of(a_tile % self._w, a_tile // self._w)
                b_ci = self._cluster_of(b_tile % self._w, b_tile // self._w)
                if a_ci == b_ci:
                    seg = _extract(self._gw_parent[a], b_tile)
                    _append_seg(tiles, seg)
                else:
                    tiles.append(b_tile)

        return tiles

    def heuristic(self, node: int, goal: int) -> int:
        w = self._w
        sx, sy = node % w, node // w
        gx, gy = goal % w, goal // w
        sci = self._cluster_of(sx, sy)
        gci = self._cluster_of(gx, gy)
        if sci == gci:
            return max(abs(sx - gx), abs(sy - gy)) * 2
        src_dist, _ = self._insert_temp(node, sci)
        dst_dist, _ = self._insert_temp(goal, gci)
        if not src_dist or not dst_dist:
            return _INF
        gw_dist = self._abstract_dijkstra_weighted(src_dist, set(dst_dist))
        best = _INF
        for dgi, dc in dst_dist.items():
            d = gw_dist.get(dgi, _INF)
            if d < _INF:
                total = d + dc
                best = min(best, total)
        return best

    def _abstract_dijkstra_weighted(
        self, sources: dict[int, int], targets: set[int]
    ) -> dict[int, int]:
        dist: dict[int, int] = {}
        heap: list[tuple[int, int]] = []
        for s, c in sources.items():
            dist[s] = c
            heapq.heappush(heap, (c, s))
        found = 0
        target_count = len(targets)
        while heap and found < target_count:
            d, node = heapq.heappop(heap)
            if d > dist.get(node, _INF):
                continue
            if node in targets:
                found += 1
            for nb, ec in self._gw_adj[node]:
                nd = d + ec
                if nd < dist.get(nb, _INF):
                    dist[nb] = nd
                    heapq.heappush(heap, (nd, nb))
        return dist


def _extract(parent: dict[int, int | None], goal: int) -> list[int]:
    path: list[int] = []
    cur: int | None = goal
    while cur is not None:
        path.append(cur)
        cur = parent.get(cur)
    path.reverse()
    return path


def _append_seg(tiles: list[int], seg: list[int]) -> None:
    if not seg:
        return
    start = 1 if tiles and seg[0] == tiles[-1] else 0
    tiles.extend(seg[start:])
