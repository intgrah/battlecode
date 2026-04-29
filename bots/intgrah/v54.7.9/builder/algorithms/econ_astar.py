from __future__ import annotations

from typing import TYPE_CHECKING, Final

from builder.algorithms.reachability import find as _uf_find
from cambc import Controller, Position, ResourceType
from util.constants import INF, MAX_N, MAX_WIDTH

if TYPE_CHECKING:
    from builder import Builder


class AStarSearch:
    TARGET_DRIFT_SQ: Final = 25
    CPU_BUDGET: Final = 17290
    BUCKET_COUNT: Final = 32
    BIDIRECTIONAL: Final = False
    """CPU budget measured as absolute turn-elapsed in microseconds (since
    ct.get_cpu_time_elapsed() returns the time since the start of the
    current turn). 1729us leaves ~270us for post-A* work before the 2ms
    server enforcement. Update() p50 is ~800us so A* typically runs for
    ~900us here; on rare slow-update turns A* may be compressed."""
    DIAG_WEIGHT: Final = 9
    """Diagonal (r²=2) is never a cardinal conveyor and never a legal bridge
    (bridges need r² in [3, 9]), so any diagonal step materialises as a
    bridge skipping to the next reachable tile along the path. Costed the
    same as a bridge so A* doesn't prefer a diagonal over a bridge unless
    the two cardinal alternatives are genuinely blocked."""
    BRIDGE_DELTAS: Final = tuple(
        (dx, dy, 9)
        for dx in range(-3, 4)
        for dy in range(-3, 4)
        if 3 <= dx * dx + dy * dy <= 9
    )
    """Bridge extra. Each step is `1 + extra`, so a bridge jump costs 10.
    Dominant cost is scaling (10% per bridge vs 1% per conveyor), not the
    base Ti cost, so a bridge should cost ~10x a cardinal conveyor."""
    CONV_NEIGHBORS: Final = (
        (1, 0, 0),
        (-1, 0, 0),
        (0, 1, 0),
        (0, -1, 0),
        (1, 1, DIAG_WEIGHT),
        (1, -1, DIAG_WEIGHT),
        (-1, 1, DIAG_WEIGHT),
        (-1, -1, DIAG_WEIGHT),
        *BRIDGE_DELTAS,
    )
    X_OF: Final = tuple(i % MAX_WIDTH for i in range(MAX_N))
    Y_OF: Final = tuple(i // MAX_WIDTH for i in range(MAX_N))

    def __init__(self, builder: Builder) -> None:
        self.builder = builder
        self.last_fail_reason: str = ""
        self.last_nodes_expanded: int = 0
        """Populated by `search` on each call that returns None. One of:
        'cpu_budget' (search paused mid-expansion; will resume next turn if
        target unchanged), 'exhausted' (all reachable tiles explored without
        finding the start — target is unreachable), 'extraction_stuck' (dist
        map complete but path reconstruction hit a dead end following the
        gradient). Empty string when the most recent call returned a path."""
        # Neighbour stencil built for full MAX_WIDTH x MAX_WIDTH. Out-of-map
        # neighbours for tiles near the actual-map boundary are filtered at
        # search time via `bfs_dist[ni] is INF` — BFS only ever relaxes real
        # tiles, so any out-of-map index has its sentinel intact. No
        # post_init prune needed; this build lives in the 5s init budget.
        self._neighbors: list[list[tuple[int, int]]] = [
            [
                (ny * MAX_WIDTH + nx, extra)
                for dx, dy, extra in AStarSearch.CONV_NEIGHBORS
                if 0 <= (nx := cx + dx) < MAX_WIDTH and 0 <= (ny := cy + dy) < MAX_WIDTH
            ]
            for cy in range(MAX_WIDTH)
            for cx in range(MAX_WIDTH)
        ]
        # Split neighbour list: cardinals (extra=0, ~4 entries) and weighted
        # (diagonals + bridges, extra=9, ~24 entries). Lets the inner loop
        # specialize: cardinal loop iterates flat ints (no tuple unpack) and
        # uses `nd = base_nd` (no extra add); weighted loop adds 9 to base_nd.
        self._cardinal_neighbors: list[list[int]] = [
            [
                ny * MAX_WIDTH + nx
                for dx, dy, extra in AStarSearch.CONV_NEIGHBORS
                if extra == 0
                and 0 <= (nx := cx + dx) < MAX_WIDTH
                and 0 <= (ny := cy + dy) < MAX_WIDTH
            ]
            for cy in range(MAX_WIDTH)
            for cx in range(MAX_WIDTH)
        ]
        self._weighted_neighbors: list[list[int]] = [
            [
                ny * MAX_WIDTH + nx
                for dx, dy, extra in AStarSearch.CONV_NEIGHBORS
                if extra != 0
                and 0 <= (nx := cx + dx) < MAX_WIDTH
                and 0 <= (ny := cy + dy) < MAX_WIDTH
            ]
            for cy in range(MAX_WIDTH)
            for cx in range(MAX_WIDTH)
        ]
        self._dist: list[int] = [INF] * MAX_N
        self._dist_bwd: list[int] = [INF] * MAX_N
        self._dist_reset: Final[tuple[int, ...]] = (INF,) * MAX_N
        self._parent_fwd: list[int] = [-1] * MAX_N
        self._parent_bwd: list[int] = [-1] * MAX_N
        self._closed_fwd: list[bool] = [False] * MAX_N
        self._closed_bwd: list[bool] = [False] * MAX_N
        self._touched_fwd: list[int] = []
        self._touched_bwd: list[int] = []
        self._buckets_fwd: list[list[int]] = [
            [] for _ in range(AStarSearch.BUCKET_COUNT)
        ]
        self._buckets_bwd: list[list[int]] = [
            [] for _ in range(AStarSearch.BUCKET_COUNT)
        ]
        # Pre-bound `.append` methods on the persistent bucket lists. Saves
        # the per-push BINARY_SUBSCR + LOAD_METHOD bytecode ops; pushes are
        # the most frequent inner-loop operation (~250/search, dominating
        # `append` time in profiles). Requires that buckets are emptied via
        # `.clear()` (preserves list identity) rather than `bk[i] = []`
        # (allocates a new list whose append we wouldn't have cached).
        self._bk_append_fwd: list = [b.append for b in self._buckets_fwd]
        self._bk_append_bwd: list = [b.append for b in self._buckets_bwd]
        self._x_heur_fwd: list[int] = [0] * MAX_WIDTH
        self._y_heur_fwd: list[int] = [0] * MAX_WIDTH
        self._x_heur_bwd: list[int] = [0] * MAX_WIDTH
        self._y_heur_bwd: list[int] = [0] * MAX_WIDTH
        self._reach_root_cache: list[int] = [-1] * MAX_N
        self._reach_root_touched: list[int] = []
        # f_at[ni] caches the f-value (g + h) of the most recent push of ni
        # into the open list. On pop, comparing f_at[ni] != cur_f is a cheap
        # stale-check: an entry is stale iff the node was re-relaxed at lower
        # cost and re-pushed into a smaller-f bucket. Saves recomputing
        # h(ni) = x_heur[x_of[ni]] + y_heur[y_of[ni]] (3 lookups + 1 add) on
        # every popped node.
        self._f_at: list[int] = [0] * MAX_N
        self._finished = True
        self._target: Position | None = None

    def search(
        self,
        ct: Controller,
        start: Position,
        target: Position,
        resource: ResourceType = ResourceType.TITANIUM,
    ) -> list[Position] | None:
        if AStarSearch.BIDIRECTIONAL:
            return self._search_bidirectional(ct, start, target, resource)
        return self._search_unidirectional(ct, start, target, resource)

    def _search_bidirectional(
        self,
        ct: Controller,
        start: Position,
        target: Position,
        resource: ResourceType = ResourceType.TITANIUM,
    ) -> list[Position] | None:
        si = start.y * MAX_WIDTH + start.x
        gi = target.y * MAX_WIDTH + target.x
        gx = target.x
        gy = target.y
        sx = start.x
        sy = start.y
        dx = abs(gx - sx)
        dy = abs(gy - sy)

        if si == gi:
            self._finished = True
            self._target = target
            self.last_fail_reason = ""
            self.last_nodes_expanded = 0
            return [start]
        if dx + dy == 1:
            self._finished = True
            self._target = target
            self.last_fail_reason = ""
            self.last_nodes_expanded = 0
            return [start, target]

        b = self.builder
        routable = (
            b.ax_routable
            if resource in (ResourceType.RAW_AXIONITE, ResourceType.REFINED_AXIONITE)
            else b.ti_routable
        )
        cost_grid = b.cost_grid
        dist_fwd = self._dist
        dist_bwd = self._dist_bwd
        parent_fwd = self._parent_fwd
        parent_bwd = self._parent_bwd
        closed_fwd = self._closed_fwd
        closed_bwd = self._closed_bwd
        touched_fwd = self._touched_fwd
        touched_bwd = self._touched_bwd
        neighbors = self._neighbors
        x_of = AStarSearch.X_OF
        y_of = AStarSearch.Y_OF
        x_heur_goal = self._x_heur_fwd
        y_heur_goal = self._y_heur_fwd
        x_heur_start = self._x_heur_bwd
        y_heur_start = self._y_heur_bwd
        for i in range(MAX_WIDTH):
            x_heur_goal[i] = abs(i - gx)
            y_heur_goal[i] = abs(i - gy)
            x_heur_start[i] = abs(i - sx)
            y_heur_start[i] = abs(i - sy)
        for idx in touched_fwd:
            dist_fwd[idx] = INF
            parent_fwd[idx] = -1
            closed_fwd[idx] = False
        touched_fwd.clear()
        for idx in touched_bwd:
            dist_bwd[idx] = INF
            parent_bwd[idx] = -1
            closed_bwd[idx] = False
        touched_bwd.clear()
        # Reachability gate: tiles outside the builder's UF component
        # are rejected for relaxation (only the target may terminate
        # there, same as the routable bypass below). Caching the root
        # once avoids re-finding it on every neighbour check.
        reach_parent = b.reach_parent
        my_root = _uf_find(reach_parent, b.my_pos.y * MAX_WIDTH + b.my_pos.x)
        find_root = _uf_find
        reach_root_cache = self._reach_root_cache
        reach_root_touched = self._reach_root_touched
        reach_root_append = reach_root_touched.append
        for cached_i in reach_root_touched:
            reach_root_cache[cached_i] = -1
        reach_root_touched.clear()
        self.last_nodes_expanded = 0
        self._target = target
        self._finished = False

        dist_fwd[si] = 0
        parent_fwd[si] = si
        touched_fwd.append(si)
        dist_bwd[gi] = 0
        parent_bwd[gi] = gi
        touched_bwd.append(gi)

        # nb_count must exceed the largest possible f-value delta from a
        # single transition or Dial's algorithm drops nodes: if a node is
        # inserted into bucket (K + delta) % nb_count where delta >= nb_count,
        # the mod-wraparound can make (K + delta) % nb_count < cur_f, and the
        # bucket gets cleared before the node is processed. Max transition
        # cost here is a bridge jump (1 + 9 = 10), so 1024 is plenty.
        nb_count = AStarSearch.BUCKET_COUNT
        bucket_mask = nb_count - 1
        f0 = x_heur_goal[sx] + y_heur_goal[sy]
        bk_fwd = self._buckets_fwd
        bk_bwd = self._buckets_bwd
        for bucket in bk_fwd:
            bucket.clear()
        for bucket in bk_bwd:
            bucket.clear()
        bk_fwd[f0 & bucket_mask].append(si)
        bk_bwd[f0 & bucket_mask].append(gi)
        cur_fwd = f0
        cur_bwd = f0
        emp_fwd = 0
        emp_bwd = 0
        best_cost = INF
        best_meet = -1

        # CPU budget is absolute turn-elapsed (not relative to A*'s own start).
        # Works now that update() is O(transport network) not O(map area);
        # on typical turns A* has ~900us here, on worst-case ~200us.
        cpu_time_elapsed = ct.get_cpu_time_elapsed
        while emp_fwd < nb_count and emp_bwd < nb_count:
            while emp_fwd < nb_count and not bk_fwd[cur_fwd & bucket_mask]:
                cur_fwd += 1
                emp_fwd += 1
            while emp_bwd < nb_count and not bk_bwd[cur_bwd & bucket_mask]:
                cur_bwd += 1
                emp_bwd += 1
            if emp_fwd >= nb_count or emp_bwd >= nb_count:
                break
            if best_cost != INF and cur_fwd >= best_cost and cur_bwd >= best_cost:
                break

            if cur_fwd <= cur_bwd:
                bucket = bk_fwd[cur_fwd & bucket_mask]
                emp_fwd = 0
                for node_i in bucket:
                    gn = dist_fwd[node_i]
                    if (
                        closed_fwd[node_i]
                        or gn + x_heur_goal[x_of[node_i]] + y_heur_goal[y_of[node_i]]
                        != cur_fwd
                    ):
                        continue
                    closed_fwd[node_i] = True
                    self.last_nodes_expanded += 1
                    other_dist = dist_bwd[node_i]
                    if other_dist != INF:
                        cand = gn + other_dist
                        if cand < best_cost:
                            best_cost = cand
                            best_meet = node_i
                    if cpu_time_elapsed() > AStarSearch.CPU_BUDGET:
                        self._finished = True
                        self.last_fail_reason = "cpu_budget"
                        return None
                    for ni, extra in neighbors[node_i]:
                        if ni != gi:
                            if not routable[ni]:
                                continue
                            rp = reach_parent[ni]
                            if rp == -1:
                                continue
                            if rp != my_root:
                                root = reach_root_cache[ni]
                                if root == -1:
                                    root = find_root(reach_parent, ni)
                                    reach_root_cache[ni] = root
                                    reach_root_append(ni)
                                if root != my_root:
                                    continue
                        nd = gn + 1 + extra
                        if nd >= dist_fwd[ni]:
                            continue
                        if dist_fwd[ni] == INF:
                            touched_fwd.append(ni)
                        dist_fwd[ni] = nd
                        parent_fwd[ni] = node_i
                        h_val = x_heur_goal[x_of[ni]] + y_heur_goal[y_of[ni]]
                        bk_fwd[(nd + h_val) & bucket_mask].append(ni)
                        other_dist = dist_bwd[ni]
                        if other_dist != INF:
                            cand = nd + other_dist
                            if cand < best_cost:
                                best_cost = cand
                                best_meet = ni
                bk_fwd[cur_fwd & bucket_mask] = []
                cur_fwd += 1
                continue
            bucket = bk_bwd[cur_bwd & bucket_mask]
            emp_bwd = 0
            for node_i in bucket:
                gn = dist_bwd[node_i]
                if (
                    closed_bwd[node_i]
                    or gn + x_heur_start[x_of[node_i]] + y_heur_start[y_of[node_i]]
                    != cur_bwd
                ):
                    continue
                closed_bwd[node_i] = True
                self.last_nodes_expanded += 1
                other_dist = dist_fwd[node_i]
                if other_dist != INF:
                    cand = gn + other_dist
                    if cand < best_cost:
                        best_cost = cand
                        best_meet = node_i
                if cpu_time_elapsed() > AStarSearch.CPU_BUDGET:
                    self._finished = True
                    self.last_fail_reason = "cpu_budget"
                    return None
                for ni, extra in neighbors[node_i]:
                    if ni != si:
                        if not routable[ni]:
                            continue
                        rp = reach_parent[ni]
                        if rp == -1:
                            continue
                        if rp != my_root:
                            root = reach_root_cache[ni]
                            if root == -1:
                                root = find_root(reach_parent, ni)
                                reach_root_cache[ni] = root
                                reach_root_append(ni)
                            if root != my_root:
                                continue
                    nd = gn + 1 + extra
                    if nd >= dist_bwd[ni]:
                        continue
                    if dist_bwd[ni] == INF:
                        touched_bwd.append(ni)
                    dist_bwd[ni] = nd
                    parent_bwd[ni] = node_i
                    h_val = x_heur_start[x_of[ni]] + y_heur_start[y_of[ni]]
                    bk_bwd[(nd + h_val) & bucket_mask].append(ni)
                    other_dist = dist_fwd[ni]
                    if other_dist != INF:
                        cand = nd + other_dist
                        if cand < best_cost:
                            best_cost = cand
                            best_meet = ni
            bk_bwd[cur_bwd & bucket_mask] = []
            cur_bwd += 1

        self._finished = True
        if best_meet == -1:
            self.last_fail_reason = "exhausted"
            return None

        rev_path: list[int] = [best_meet]
        node = best_meet
        append_rev = rev_path.append
        while node != si:
            node = parent_fwd[node]
            if node == -1:
                self.last_fail_reason = "extraction_stuck"
                return None
            append_rev(node)
        rev_path.reverse()
        node = best_meet
        while node != gi:
            node = parent_bwd[node]
            if node == -1:
                self.last_fail_reason = "extraction_stuck"
                return None
            rev_path.append(node)

        self.last_fail_reason = ""
        return [Position(x_of[i], y_of[i]) for i in rev_path]

    def _search_unidirectional(
        self,
        ct: Controller,
        start: Position,
        target: Position,
        resource: ResourceType = ResourceType.TITANIUM,
    ) -> list[Position] | None:
        si = start.y * MAX_WIDTH + start.x
        gi = target.y * MAX_WIDTH + target.x
        resumed_search = False

        # Cross-turn resumption: reset `_dist` only when the previous search
        # finished or the target has drifted. Otherwise keep accumulated
        # distances so the search can continue where the last turn's CPU
        # budget ran out. Cost-grid mutations between turns may leave some
        # stale dist values, but the greedy path extraction still follows a
        # decreasing gradient, and re-exploration of relaxed neighbours
        # typically corrects any local suboptimality.
        if (
            self._finished
            or self._target is None
            or target.distance_squared(self._target) > AStarSearch.TARGET_DRIFT_SQ
        ):
            self._dist[:] = self._dist_reset
            self._target = target
        else:
            resumed_search = True
            target = self._target
            gi = target.y * MAX_WIDTH + target.x

        b = self.builder
        routable = (
            b.ax_routable
            if resource in (ResourceType.RAW_AXIONITE, ResourceType.REFINED_AXIONITE)
            else b.ti_routable
        )
        cost_grid = b.cost_grid
        dist = self._dist
        neighbors = self._neighbors
        cardinal_neighbors = self._cardinal_neighbors
        weighted_neighbors = self._weighted_neighbors
        sx = start.x
        sy = start.y
        x_of = AStarSearch.X_OF
        y_of = AStarSearch.Y_OF
        x_heur = self._x_heur_fwd
        y_heur = self._y_heur_fwd
        for i in range(MAX_WIDTH):
            x_heur[i] = abs(i - sx)
            y_heur[i] = abs(i - sy)
        # Reachability gate: tiles outside the builder's UF component
        # are rejected for relaxation (only the target may terminate
        # there, same as the routable bypass below). Caching the root
        # once avoids re-finding it on every neighbour check.
        reach_parent = b.reach_parent
        my_root = _uf_find(reach_parent, b.my_pos.y * MAX_WIDTH + b.my_pos.x)
        find_root = _uf_find
        reach_root_cache = self._reach_root_cache
        reach_root_touched = self._reach_root_touched
        reach_root_append = reach_root_touched.append
        for cached_i in reach_root_touched:
            reach_root_cache[cached_i] = -1
        reach_root_touched.clear()
        # Local counter to avoid `self.x += 1` attribute access in hot loop.
        nodes_expanded = 0

        if dist[gi] is INF:
            dist[gi] = 0

        # nb_count must exceed the largest possible f-value delta from a
        # single transition or Dial's algorithm drops nodes: if a node is
        # inserted into bucket (K + delta) % nb_count where delta >= nb_count,
        # the mod-wraparound can make (K + delta) % nb_count < cur_f, and the
        # bucket gets cleared before the node is processed. Max transition
        # cost here is a bridge jump (1 + 9 = 10), so 1024 is plenty.
        nb_count = AStarSearch.BUCKET_COUNT
        bucket_mask = nb_count - 1
        gx, gy = target.x, target.y
        f0 = x_heur[gx] + y_heur[gy]
        bk = self._buckets_fwd
        bk_append = self._bk_append_fwd
        for bucket in bk:
            bucket.clear()
        bk_append[f0 & bucket_mask](gi)
        f_at = self._f_at
        f_at[gi] = f0
        cur_f = f0
        emp = 0

        # CPU budget is absolute turn-elapsed (not relative to A*'s own start).
        # Works now that update() is O(transport network) not O(map area);
        # on typical turns A* has ~900us here, on worst-case ~200us.
        cpu_time_elapsed = ct.get_cpu_time_elapsed
        cpu_budget = AStarSearch.CPU_BUDGET
        found = False
        while emp < nb_count:
            bucket = bk[cur_f & bucket_mask]
            if not bucket:
                cur_f += 1
                emp += 1
                continue
            # CPU budget check at bucket boundaries only. A bucket's worth of
            # work (typical: 1-5 entries × ~1µs each) is the slop budget; in
            # exchange we drop the per-pop call which the profile showed at
            # ~70 calls/search. Slow real-game cases visit ~50 buckets so we
            # still get frequent enough checks to honour the budget.
            if cpu_time_elapsed() > cpu_budget:
                self._finished = False
                self.last_fail_reason = "cpu_budget"
                self.last_nodes_expanded = nodes_expanded
                return None
            emp = 0
            for node_i in bucket:
                if f_at[node_i] != cur_f:
                    continue
                nodes_expanded += 1
                if node_i == si:
                    found = True
                    break
                gn = dist[node_i]
                base_nd = gn + 1
                weighted_nd = base_nd + 9
                # Cardinal neighbours: flat int list, no `extra` add per step.
                # Note: the goal tile `gi` is pre-initialised to dist=0 above,
                # so any relaxation attempt of `gi` from its neighbours gets
                # filtered by `base_nd >= dist[ni]` (since dist[gi]=0 < base_nd
                # always). That makes the routable/reach gates safe to apply
                # unconditionally — gi will fall through to the dist check
                # whether it passes the gates or not — saving a per-neighbour
                # `if ni != gi:` int compare on the hot path.
                for ni in cardinal_neighbors[node_i]:
                    if not routable[ni]:
                        continue
                    rp = reach_parent[ni]
                    if rp != my_root:
                        if rp == -1:
                            continue
                        root = reach_root_cache[ni]
                        if root == -1:
                            root = find_root(reach_parent, ni)
                            reach_root_cache[ni] = root
                            reach_root_append(ni)
                        if root != my_root:
                            continue
                    if base_nd >= dist[ni]:
                        continue
                    dist[ni] = base_nd
                    nf = base_nd + x_heur[x_of[ni]] + y_heur[y_of[ni]]
                    f_at[ni] = nf
                    bk_append[nf & bucket_mask](ni)
                # Weighted neighbours: diagonals + bridges (extra always 9,
                # so cost is `base_nd + 9` precomputed as `weighted_nd`).
                for ni in weighted_neighbors[node_i]:
                    if not routable[ni]:
                        continue
                    rp = reach_parent[ni]
                    if rp != my_root:
                        if rp == -1:
                            continue
                        root = reach_root_cache[ni]
                        if root == -1:
                            root = find_root(reach_parent, ni)
                            reach_root_cache[ni] = root
                            reach_root_append(ni)
                        if root != my_root:
                            continue
                    if weighted_nd >= dist[ni]:
                        continue
                    dist[ni] = weighted_nd
                    nf = weighted_nd + x_heur[x_of[ni]] + y_heur[y_of[ni]]
                    f_at[ni] = nf
                    bk_append[nf & bucket_mask](ni)
            if found:
                break
            bk[cur_f & bucket_mask].clear()
            cur_f += 1

        self._finished = True
        self.last_nodes_expanded = nodes_expanded
        if not found:
            self.last_fail_reason = "exhausted"
            return None

        path: list[int] = [si]
        node = si
        cur_d = dist[si]
        append_path = path.append
        if resumed_search:
            while node != gi:
                best_dist = cur_d
                best = node
                for ni, extra in neighbors[node]:
                    d = dist[ni]
                    if d is INF:
                        continue
                    # Non-routable tiles (unreachable OR not buildable OR leakage)
                    # may only appear as the terminal target, never as an
                    # intermediate step on the path.
                    if ni != gi:
                        if not routable[ni]:
                            continue
                        rp = reach_parent[ni]
                        if rp == -1:
                            continue
                        if rp != my_root:
                            root = reach_root_cache[ni]
                            if root == -1:
                                root = find_root(reach_parent, ni)
                                reach_root_cache[ni] = root
                                reach_root_append(ni)
                            if root != my_root:
                                continue
                    d += extra
                    if d < best_dist:
                        best_dist = d
                        best = ni
                if best == node:
                    self.last_fail_reason = "extraction_stuck"
                    return None
                append_path(best)
                node = best
                cur_d = best_dist
        else:
            while node != gi:
                best_dist = cur_d
                best = node
                for ni, extra in neighbors[node]:
                    d = dist[ni]
                    if d is INF:
                        continue
                    d += extra
                    if d < best_dist:
                        best_dist = d
                        best = ni
                if best == node:
                    self.last_fail_reason = "extraction_stuck"
                    return None
                append_path(best)
                node = best
                cur_d = best_dist

        self.last_fail_reason = ""
        return [Position(x_of[i], y_of[i]) for i in path]

    def search_blocked(
        self,
        ct: Controller,
        start: Position,
        goal: Position,
    ) -> list[Position] | None:
        """Run `search` but treat tiles occupied by other friendly bots as
        non-routable. Mutates `ti_routable` / `ax_routable` temporarily.
        """
        b = self.builder
        saved: list[tuple[int, bool, bool]] = []
        for pos in b.nearby_tiles:
            if pos in b.all_bots and pos != start:
                idx = pos.y * MAX_WIDTH + pos.x
                saved.append((idx, b.ti_routable[idx], b.ax_routable[idx]))
                b.ti_routable[idx] = False
                b.ax_routable[idx] = False
        result = self.search(ct, start, goal)
        for idx, ti_val, ax_val in saved:
            b.ti_routable[idx] = ti_val
            b.ax_routable[idx] = ax_val
        return result
