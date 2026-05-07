"""
Translation of `bots/intgrah/v54.7.9/builder/algorithms/econ_astar.py`.

A*-on-Dial conveyor router. The `AStarSearch` instance keeps long-lived
buckets / bookkeeping so a paused search can resume next turn.
"""

from __future__ import annotations

from typing import Final

from cambc import Position, ResourceType
from util.constants import MAX_N

from builder.algorithms.reachability import find as uf_find

TARGET_DRIFT_SQ: Final[int] = 25
BUCKET_COUNT: Final[int] = 32
BIDIRECTIONAL: Final[bool] = False
DIAG_WEIGHT: Final[int] = 9
"""
Diagonal (r²=2) is never a cardinal conveyor and never a legal bridge
(bridges need r² in [3, 9]), so any diagonal step materialises as a
bridge skipping to the next reachable tile along the path. Costed the
same as a bridge so A* doesn't prefer a diagonal over a bridge unless
the two cardinal alternatives are genuinely blocked.
"""


def bridge_deltas():
    out: list[tuple[int, int, int]] = []
    for dx in range(-3, (3) + 1):
        for dy in range(-3, (3) + 1):
            d2 = dx * dx + dy * dy
            if d2 in range(3, (9) + 1):
                out.append((dx, dy, 9))
    return out


def conv_neighbors():
    out: list[tuple[int, int, int]] = [
        (1, 0, 0),
        (-1, 0, 0),
        (0, 1, 0),
        (0, -1, 0),
        (1, 1, 9),
        (1, -1, 9),
        (-1, 1, 9),
        (-1, -1, 9),
    ]
    out.extend(bridge_deltas())
    return out


def x_of_table():
    out = [0] * MAX_N
    for i in range(MAX_N):
        out[i] = int(i % 50)
    return out


def y_of_table():
    out = [0] * MAX_N
    for i in range(MAX_N):
        out[i] = int(i // 50)
    return out


class EconAstarCtx:
    """
    Subset of `Builder` state read/written by the A* search. The Builder
    struct (Phase G6) embeds an instance of this and passes it to each
    `search` call; the algorithm code never touches the rest of the Builder.
    """

    ax_routable: list[bool]
    ti_routable: list[bool]
    routing_extra: list[int]
    reach_parent: list[int]
    my_pos: Position
    nearby_tiles: list[Position]
    all_bots: dict[Position, int]

    def __init__(
        self,
        ax_routable: list[bool],
        ti_routable: list[bool],
        routing_extra: list[int],
        reach_parent: list[int],
        my_pos: Position,
        nearby_tiles: list[Position],
        all_bots: dict[Position, int],
    ) -> None:
        self.ax_routable = ax_routable
        self.ti_routable = ti_routable
        self.routing_extra = routing_extra
        self.reach_parent = reach_parent
        self.my_pos = my_pos
        self.nearby_tiles = nearby_tiles
        self.all_bots = all_bots


class AStarSearch:
    last_fail_reason: str
    last_nodes_expanded: int
    neighbors: list[list[tuple[int, int]]]
    cardinal_neighbors: list[list[int]]
    weighted_neighbors: list[list[int]]
    _dist: list[int]
    dist_bwd: list[int]
    parent_fwd: list[int]
    parent_bwd: list[int]
    closed_fwd: list[bool]
    closed_bwd: list[bool]
    touched_fwd: list[int]
    touched_bwd: list[int]
    buckets_fwd: list[list[int]]
    buckets_bwd: list[list[int]]
    x_heur_fwd: list[int]
    y_heur_fwd: list[int]
    x_heur_bwd: list[int]
    y_heur_bwd: list[int]
    reach_root_cache: list[int]
    reach_root_touched: list[int]
    f_at: list[int]
    finished: bool
    target: Position | None
    x_of: list[int]
    y_of: list[int]

    def __init__(self) -> None:
        """Construct a fresh search with all per-tile data structures pre-allocated."""
        neighbors_template = conv_neighbors()
        neighbors: list[list[tuple[int, int]]] = [[] for _ in range(MAX_N)]
        cardinal_neighbors: list[list[int]] = [[] for _ in range(MAX_N)]
        weighted_neighbors: list[list[int]] = [[] for _ in range(MAX_N)]
        for cy in range(50):
            for cx in range(50):
                i = int(cy * 50 + cx)
                for dx, dy, extra in neighbors_template:
                    nx = cx + dx
                    ny = cy + dy
                    if nx >= 0 and nx < 50 and ny >= 0 and ny < 50:
                        ni = ny * 50 + nx
                        neighbors[i].append((ni, extra))
                        if extra == 0:
                            cardinal_neighbors[i].append(ni)
                        else:
                            weighted_neighbors[i].append(ni)
        self.last_fail_reason = ""
        self.last_nodes_expanded = 0
        self.neighbors = neighbors
        self.cardinal_neighbors = cardinal_neighbors
        self.weighted_neighbors = weighted_neighbors
        self._dist = [1000000] * MAX_N
        self.dist_bwd = [1000000] * MAX_N
        self.parent_fwd = [-1] * MAX_N
        self.parent_bwd = [-1] * MAX_N
        self.closed_fwd = [False] * MAX_N
        self.closed_bwd = [False] * MAX_N
        self.touched_fwd = []
        self.touched_bwd = []
        self.buckets_fwd = [[] for _ in range(32)]
        self.buckets_bwd = [[] for _ in range(32)]
        self.x_heur_fwd = [0] * 50
        self.y_heur_fwd = [0] * 50
        self.x_heur_bwd = [0] * 50
        self.y_heur_bwd = [0] * 50
        self.reach_root_cache = [-1] * MAX_N
        self.reach_root_touched = []
        self.f_at = [0] * MAX_N
        self.finished = True
        self.target = None
        self.x_of = x_of_table()
        self.y_of = y_of_table()

    def search(self, start, target, resource, ctx):
        if False:
            return self.search_bidirectional(start, target, resource, ctx)
        return self.search_unidirectional(start, target, resource, ctx)

    def search_bidirectional(self, start, target, resource, ctx):
        stride = 50
        si = start.y * stride + start.x
        gi = target.y * stride + target.x
        gx = target.x
        gy = target.y
        sx = start.x
        sy = start.y
        dx = abs(gx - sx)
        dy = abs(gy - sy)
        if si == gi:
            self.finished = True
            self.target = target
            self.last_fail_reason = ""
            self.last_nodes_expanded = 0
            return [start]
        if dx + dy == 1:
            self.finished = True
            self.target = target
            self.last_fail_reason = ""
            self.last_nodes_expanded = 0
            return [start, target]
        routable: list[bool] = (
            ctx.ax_routable
            if (resource in (ResourceType.RAW_AXIONITE, ResourceType.REFINED_AXIONITE))
            else ctx.ti_routable
        )
        routing_extra = ctx.routing_extra
        for i in range(50):
            self.x_heur_fwd[i] = abs(int(i) - gx)
            self.y_heur_fwd[i] = abs(int(i) - gy)
            self.x_heur_bwd[i] = abs(int(i) - sx)
            self.y_heur_bwd[i] = abs(int(i) - sy)
        for idx in self.touched_fwd:
            self._dist[int(idx)] = 1000000
            self.parent_fwd[int(idx)] = -1
            self.closed_fwd[int(idx)] = False
        self.touched_fwd.clear()
        for idx in self.touched_bwd:
            self.dist_bwd[int(idx)] = 1000000
            self.parent_bwd[int(idx)] = -1
            self.closed_bwd[int(idx)] = False
        self.touched_bwd.clear()
        my_root = uf_find(ctx.reach_parent, ctx.my_pos.y * stride + ctx.my_pos.x)
        for cached_i in self.reach_root_touched:
            self.reach_root_cache[int(cached_i)] = -1
        self.reach_root_touched.clear()
        self.last_nodes_expanded = 0
        self.target = target
        self.finished = False
        self._dist[int(si)] = 0
        self.parent_fwd[int(si)] = si
        self.touched_fwd.append(si)
        self.dist_bwd[int(gi)] = 0
        self.parent_bwd[int(gi)] = gi
        self.touched_bwd.append(gi)
        nb_count = 32
        bucket_mask = nb_count - 1
        f0 = self.x_heur_fwd[int(sx)] + self.y_heur_fwd[int(sy)]
        for bucket in self.buckets_fwd:
            bucket.clear()
        for bucket in self.buckets_bwd:
            bucket.clear()
        self.buckets_fwd[int(f0 & bucket_mask)].append(si)
        self.buckets_bwd[int(f0 & bucket_mask)].append(gi)
        cur_fwd = f0
        cur_bwd = f0
        emp_fwd: int = 0
        emp_bwd: int = 0
        best_cost = 1000000
        best_meet: int = -1
        while emp_fwd < nb_count and emp_bwd < nb_count:
            while emp_fwd < nb_count and (
                not self.buckets_fwd[int(cur_fwd & bucket_mask)]
            ):
                cur_fwd += 1
                emp_fwd += 1
            while emp_bwd < nb_count and (
                not self.buckets_bwd[int(cur_bwd & bucket_mask)]
            ):
                cur_bwd += 1
                emp_bwd += 1
            if emp_fwd >= nb_count or emp_bwd >= nb_count:
                break
            if best_cost != 1000000 and cur_fwd >= best_cost and cur_bwd >= best_cost:
                break
            if cur_fwd <= cur_bwd:
                slot_fwd = int(cur_fwd & bucket_mask)
                emp_fwd = 0
                idx = 0
                while idx < len(self.buckets_fwd[slot_fwd]):
                    node_i = self.buckets_fwd[slot_fwd][idx]
                    idx += 1
                    gn = self._dist[int(node_i)]
                    if (
                        self.closed_fwd[int(node_i)]
                        or gn
                        + self.x_heur_fwd[int(self.x_of[int(node_i)])]
                        + self.y_heur_fwd[int(self.y_of[int(node_i)])]
                        != cur_fwd
                    ):
                        continue
                    self.closed_fwd[int(node_i)] = True
                    self.last_nodes_expanded += 1
                    other_dist = self.dist_bwd[int(node_i)]
                    if other_dist != 1000000:
                        cand = gn + other_dist
                        if cand < best_cost:
                            best_cost = cand
                            best_meet = node_i
                    nbrs = self.neighbors[int(node_i)]
                    for ni, extra in nbrs:
                        if ni != gi:
                            if not routable[int(ni)]:
                                continue
                            rp = ctx.reach_parent[int(ni)]
                            if rp == -1:
                                continue
                            if rp != my_root:
                                root = self.reach_root_cache[int(ni)]
                                if root == -1:
                                    root = uf_find(ctx.reach_parent, ni)
                                    self.reach_root_cache[int(ni)] = root
                                    self.reach_root_touched.append(ni)
                                if root != my_root:
                                    continue
                        nd = gn + 1 + extra + int(routing_extra[int(ni)])
                        if nd >= self._dist[int(ni)]:
                            continue
                        if self._dist[int(ni)] == 1000000:
                            self.touched_fwd.append(ni)
                        self._dist[int(ni)] = nd
                        self.parent_fwd[int(ni)] = node_i
                        h_val = (
                            self.x_heur_fwd[int(self.x_of[int(ni)])]
                            + self.y_heur_fwd[int(self.y_of[int(ni)])]
                        )
                        self.buckets_fwd[int(nd + h_val & bucket_mask)].append(ni)
                        other_dist = self.dist_bwd[int(ni)]
                        if other_dist != 1000000:
                            cand = nd + other_dist
                            if cand < best_cost:
                                best_cost = cand
                                best_meet = ni
                self.buckets_fwd[slot_fwd].clear()
                cur_fwd += 1
                continue
            slot_bwd = int(cur_bwd & bucket_mask)
            emp_bwd = 0
            idx = 0
            while idx < len(self.buckets_bwd[slot_bwd]):
                node_i = self.buckets_bwd[slot_bwd][idx]
                idx += 1
                gn = self.dist_bwd[int(node_i)]
                if (
                    self.closed_bwd[int(node_i)]
                    or gn
                    + self.x_heur_bwd[int(self.x_of[int(node_i)])]
                    + self.y_heur_bwd[int(self.y_of[int(node_i)])]
                    != cur_bwd
                ):
                    continue
                self.closed_bwd[int(node_i)] = True
                self.last_nodes_expanded += 1
                other_dist = self._dist[int(node_i)]
                if other_dist != 1000000:
                    cand = gn + other_dist
                    if cand < best_cost:
                        best_cost = cand
                        best_meet = node_i
                nbrs = self.neighbors[int(node_i)]
                for ni, extra in nbrs:
                    if ni != si:
                        if not routable[int(ni)]:
                            continue
                        rp = ctx.reach_parent[int(ni)]
                        if rp == -1:
                            continue
                        if rp != my_root:
                            root = self.reach_root_cache[int(ni)]
                            if root == -1:
                                root = uf_find(ctx.reach_parent, ni)
                                self.reach_root_cache[int(ni)] = root
                                self.reach_root_touched.append(ni)
                            if root != my_root:
                                continue
                    nd = gn + 1 + extra + int(routing_extra[int(ni)])
                    if nd >= self.dist_bwd[int(ni)]:
                        continue
                    if self.dist_bwd[int(ni)] == 1000000:
                        self.touched_bwd.append(ni)
                    self.dist_bwd[int(ni)] = nd
                    self.parent_bwd[int(ni)] = node_i
                    h_val = (
                        self.x_heur_bwd[int(self.x_of[int(ni)])]
                        + self.y_heur_bwd[int(self.y_of[int(ni)])]
                    )
                    self.buckets_bwd[int(nd + h_val & bucket_mask)].append(ni)
                    other_dist = self._dist[int(ni)]
                    if other_dist != 1000000:
                        cand = nd + other_dist
                        if cand < best_cost:
                            best_cost = cand
                            best_meet = ni
            self.buckets_bwd[slot_bwd].clear()
            cur_bwd += 1
        self.finished = True
        if best_meet == -1:
            self.last_fail_reason = "exhausted"
            return None
        rev_path: list[int] = [best_meet]
        node = best_meet
        while node != si:
            node = self.parent_fwd[int(node)]
            if node == -1:
                self.last_fail_reason = "extraction_stuck"
                return None
            rev_path.append(node)
        rev_path.reverse()
        node = best_meet
        while node != gi:
            node = self.parent_bwd[int(node)]
            if node == -1:
                self.last_fail_reason = "extraction_stuck"
                return None
            rev_path.append(node)
        self.last_fail_reason = ""
        return [Position(x=self.x_of[int(i)], y=self.y_of[int(i)]) for i in rev_path]

    def search_unidirectional(self, start, target, resource, ctx):
        stride = 50
        si = start.y * stride + start.x
        gi = target.y * stride + target.x
        resumed_search = False
        target = target
        if (
            self.finished
            or (self.target is None)
            or target.distance_squared(self.target) > 25
        ):
            self._dist[:] = [1000000] * len(self._dist)
            self.target = target
        else:
            resumed_search = True
            target = self.target
            gi = target.y * stride + target.x
        routable: list[bool] = (
            ctx.ax_routable
            if (resource in (ResourceType.RAW_AXIONITE, ResourceType.REFINED_AXIONITE))
            else ctx.ti_routable
        )
        routing_extra = ctx.routing_extra
        sx = start.x
        sy = start.y
        for i in range(50):
            self.x_heur_fwd[i] = abs(int(i) - sx)
            self.y_heur_fwd[i] = abs(int(i) - sy)
        my_root = uf_find(ctx.reach_parent, ctx.my_pos.y * stride + ctx.my_pos.x)
        for cached_i in self.reach_root_touched:
            self.reach_root_cache[int(cached_i)] = -1
        self.reach_root_touched.clear()
        nodes_expanded = 0
        if self._dist[int(gi)] == 1000000:
            self._dist[int(gi)] = 0
        nb_count = 32
        bucket_mask = nb_count - 1
        gx = target.x
        gy = target.y
        f0 = self.x_heur_fwd[int(gx)] + self.y_heur_fwd[int(gy)]
        for bucket in self.buckets_fwd:
            bucket.clear()
        self.buckets_fwd[int(f0 & bucket_mask)].append(gi)
        self.f_at[int(gi)] = f0
        cur_f = f0
        emp: int = 0
        found = False
        while emp < nb_count:
            if not self.buckets_fwd[int(cur_f & bucket_mask)]:
                cur_f += 1
                emp += 1
                continue
            emp = 0
            slot = int(cur_f & bucket_mask)
            idx = 0
            while idx < len(self.buckets_fwd[slot]):
                node_i = self.buckets_fwd[slot][idx]
                idx += 1
                if self.f_at[int(node_i)] != cur_f:
                    continue
                nodes_expanded += 1
                if node_i == si:
                    found = True
                    break
                gn = self._dist[int(node_i)]
                base_nd = gn + 1
                weighted_nd = base_nd + 9
                cardinals = self.cardinal_neighbors[int(node_i)]
                for ni in cardinals:
                    if not routable[int(ni)]:
                        continue
                    rp = ctx.reach_parent[int(ni)]
                    if rp != my_root:
                        if rp == -1:
                            continue
                        root = self.reach_root_cache[int(ni)]
                        if root == -1:
                            root = uf_find(ctx.reach_parent, ni)
                            self.reach_root_cache[int(ni)] = root
                            self.reach_root_touched.append(ni)
                        if root != my_root:
                            continue
                    nd = base_nd + int(routing_extra[int(ni)])
                    if nd >= self._dist[int(ni)]:
                        continue
                    self._dist[int(ni)] = nd
                    nf = (
                        nd
                        + self.x_heur_fwd[int(self.x_of[int(ni)])]
                        + self.y_heur_fwd[int(self.y_of[int(ni)])]
                    )
                    self.f_at[int(ni)] = nf
                    self.buckets_fwd[int(nf & bucket_mask)].append(ni)
                weighted = self.weighted_neighbors[int(node_i)]
                for ni in weighted:
                    if not routable[int(ni)]:
                        continue
                    rp = ctx.reach_parent[int(ni)]
                    if rp != my_root:
                        if rp == -1:
                            continue
                        root = self.reach_root_cache[int(ni)]
                        if root == -1:
                            root = uf_find(ctx.reach_parent, ni)
                            self.reach_root_cache[int(ni)] = root
                            self.reach_root_touched.append(ni)
                        if root != my_root:
                            continue
                    nd = weighted_nd + int(routing_extra[int(ni)])
                    if nd >= self._dist[int(ni)]:
                        continue
                    self._dist[int(ni)] = nd
                    nf = (
                        nd
                        + self.x_heur_fwd[int(self.x_of[int(ni)])]
                        + self.y_heur_fwd[int(self.y_of[int(ni)])]
                    )
                    self.f_at[int(ni)] = nf
                    self.buckets_fwd[int(nf & bucket_mask)].append(ni)
            self.buckets_fwd[slot].clear()
            if found:
                break
            cur_f += 1
        self.finished = True
        self.last_nodes_expanded = nodes_expanded
        if not found:
            self.last_fail_reason = "exhausted"
            return None
        path: list[int] = [si]
        node = si
        cur_d = self._dist[int(si)]
        if resumed_search:
            while node != gi:
                best_dist = cur_d
                best = node
                nbrs = self.neighbors[int(node)]
                for ni, extra in nbrs:
                    d = self._dist[int(ni)]
                    if d == 1000000:
                        continue
                    if ni != gi:
                        if not routable[int(ni)]:
                            continue
                        rp = ctx.reach_parent[int(ni)]
                        if rp == -1:
                            continue
                        if rp != my_root:
                            root = self.reach_root_cache[int(ni)]
                            if root == -1:
                                root = uf_find(ctx.reach_parent, ni)
                                self.reach_root_cache[int(ni)] = root
                                self.reach_root_touched.append(ni)
                            if root != my_root:
                                continue
                    d += extra
                    if d < best_dist:
                        best_dist = d
                        best = ni
                if best == node:
                    self.last_fail_reason = "extraction_stuck"
                    return None
                path.append(best)
                node = best
                cur_d = best_dist
        else:
            while node != gi:
                best_dist = cur_d
                best = node
                nbrs = self.neighbors[int(node)]
                for ni, extra in nbrs:
                    d = self._dist[int(ni)]
                    if d == 1000000:
                        continue
                    d += extra
                    if d < best_dist:
                        best_dist = d
                        best = ni
                if best == node:
                    self.last_fail_reason = "extraction_stuck"
                    return None
                path.append(best)
                node = best
                cur_d = best_dist
        self.last_fail_reason = ""
        return [Position(x=self.x_of[int(i)], y=self.y_of[int(i)]) for i in path]

    def search_blocked(self, start, goal, ctx):
        """
        Run `search` but treat tiles occupied by other friendly bots as
        non-routable. Mutates `ti_routable` / `ax_routable` temporarily.
        """
        stride = 50
        saved: list[tuple[int, bool, bool]] = []
        nearby = list(ctx.nearby_tiles)
        for pos in nearby:
            if (pos in ctx.all_bots) and pos != start:
                idx = int(pos.y * stride + pos.x)
                saved.append((idx, ctx.ti_routable[idx], ctx.ax_routable[idx]))
                ctx.ti_routable[idx] = False
                ctx.ax_routable[idx] = False
        result = self.search(start, goal, ResourceType.TITANIUM, ctx)
        for idx, ti_val, ax_val in saved:
            ctx.ti_routable[idx] = ti_val
            ctx.ax_routable[idx] = ax_val
        return result

    @staticmethod
    def default():
        return AStarSearch()
