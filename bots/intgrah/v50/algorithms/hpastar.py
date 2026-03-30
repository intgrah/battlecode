from __future__ import annotations

import heapq
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

_INF = 1_000_000
_DIR8 = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))


class GatewayGraph:
    __slots__ = (
        "_ch",
        "_cluster_gws",
        "_cs",
        "_cw",
        "_dirty",
        "_gateways",
        "_gw_adj",
        "_gw_cluster",
        "_gw_parent",
        "_gw_tile",
        "_h",
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
        self._cs = cluster_size
        self._cw = (w + cluster_size - 1) // cluster_size
        self._ch = (h + cluster_size - 1) // cluster_size
        self._tile_cost = tile_cost

        self._gateways: list[tuple[int, int]] = []
        self._gw_tile: list[int] = []
        self._gw_cluster: list[tuple[int, int]] = []
        self._gw_adj: list[list[tuple[int, int]]] = []
        self._gw_parent: list[dict[int, int | None]] = []
        self._cluster_gws: list[list[int]] = [[] for _ in range(self._cw * self._ch)]
        self._dirty: set[int] = set()

        self._build_all()

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
        return self._tile_cost(x, y) < _INF

    def _step_cost(self, x0: int, y0: int, x1: int, y1: int) -> int:
        c = self._tile_cost(x1, y1)
        if c >= _INF:
            return _INF
        if x0 != x1 and y0 != y1:
            c += 1
        return c

    def _build_all(self) -> None:
        self._gateways.clear()
        self._gw_tile.clear()
        self._gw_cluster.clear()
        self._gw_adj.clear()
        self._gw_parent.clear()
        for cg in self._cluster_gws:
            cg.clear()

        self._find_gateways()
        self._compute_intra_edges()

    def _add_gateway(self, x0: int, y0: int, x1: int, y1: int) -> None:
        ci_a = self._cluster_of(x0, y0)
        ci_b = self._cluster_of(x1, y1)
        t0 = y0 * self._w + x0
        t1 = y1 * self._w + x1
        gi_a = len(self._gw_tile)
        self._gw_tile.append(t0)
        self._gw_cluster.append((ci_a, ci_b))
        self._gw_adj.append([])
        self._gw_parent.append({})
        self._cluster_gws[ci_a].append(gi_a)
        gi_b = len(self._gw_tile)
        self._gw_tile.append(t1)
        self._gw_cluster.append((ci_b, ci_a))
        self._gw_adj.append([])
        self._gw_parent.append({})
        self._cluster_gws[ci_b].append(gi_b)
        cost = self._step_cost(x0, y0, x1, y1)
        self._gw_adj[gi_a].append((gi_b, cost))
        self._gw_adj[gi_b].append((gi_a, cost))
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

    def _cluster_dijkstra(
        self, start: int, x0: int, y0: int, x1: int, y1: int
    ) -> tuple[dict[int, int], dict[int, int | None]]:
        w = self._w
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
                nd = d + self._step_cost(nx_base, ny_base, nx, ny)
                if nd >= _INF:
                    continue
                ni = ny * w + nx
                if nd < dist.get(ni, _INF):
                    dist[ni] = nd
                    parent[ni] = node
                    heapq.heappush(heap, (nd, ni))
        return dist, parent

    def invalidate_tile(self, x: int, y: int) -> None:
        ci = self._cluster_of(x, y)
        self._dirty.add(ci)
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
        self._tile_cost = tile_cost
        self._build_all()
        self._dirty.clear()

    def _local_dijkstra(
        self, si: int, gi: int, x0: int, y0: int, x1: int, y1: int
    ) -> list[int] | None:
        """Dijkstra within an arbitrary rectangular region."""
        w = self._w
        dist: dict[int, int] = {si: 0}
        parent: dict[int, int | None] = {si: None}
        heap: list[tuple[int, int]] = [(0, si)]
        while heap:
            d, node = heapq.heappop(heap)
            if node == gi:
                return _extract(parent, gi)
            if d > dist.get(node, _INF):
                continue
            nx_base, ny_base = node % w, node // w
            for dx, dy in _DIR8:
                nx, ny = nx_base + dx, ny_base + dy
                if nx < x0 or nx >= x1 or ny < y0 or ny >= y1:
                    continue
                nd = d + self._step_cost(nx_base, ny_base, nx, ny)
                if nd >= _INF:
                    continue
                ni = ny * w + nx
                if nd < dist.get(ni, _INF):
                    dist[ni] = nd
                    parent[ni] = node
                    heapq.heappush(heap, (nd, ni))
        return None

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
            _, parent = self._cluster_dijkstra(si, x0, y0, x1, y1)
            if gi in parent:
                return _extract(parent, gi)

        # Local search for nearby points in adjacent clusters.
        # Merge the bounding boxes of both clusters (clamped to map) and
        # run a single Dijkstra.  Cheap because the region is at most
        # 2×cluster_size in each dimension.
        scx, scy = divmod(sci, self._cw)
        gcx, gcy = divmod(gci, self._cw)
        if abs(scy - gcy) <= 1 and abs(scx - gcx) <= 1:
            sx0, sy0, sx1, sy1 = self._cluster_bounds(sci)
            gx0, gy0, gx1, gy1 = self._cluster_bounds(gci)
            lx0 = min(sx0, gx0)
            ly0 = min(sy0, gy0)
            lx1 = max(sx1, gx1)
            ly1 = max(sy1, gy1)
            local = self._local_dijkstra(si, gi, lx0, ly0, lx1, ly1)
            if local is not None:
                return local

        src_dist, src_parent = self._insert_temp(si, sci)
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

        for gi_idx, cost in src_dist.items():
            g[gi_idx] = cost
            ab_parent[gi_idx] = src_node
            tx, ty = self._gw_tile[gi_idx] % w, self._gw_tile[gi_idx] // w
            h = max(abs(tx - gx_f), abs(ty - gy_f)) * 2
            heapq.heappush(heap, (cost + h, gi_idx, cost))

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

            for nb, cost in self._gw_adj[node]:
                nd = d + cost
                if nd < g.get(nb, _INF):
                    g[nb] = nd
                    ab_parent[nb] = node
                    tx, ty = self._gw_tile[nb] % w, self._gw_tile[nb] // w
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
            for nb, cost in self._gw_adj[node]:
                nd = d + cost
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
