from __future__ import annotations

from typing import TYPE_CHECKING, Final

from cambc import Controller, Position, ResourceType
from util.constants import INF, MAX_N, MAX_WIDTH

if TYPE_CHECKING:
    from builder import Builder


class AStarSearch:
    TARGET_DRIFT_SQ: Final = 25
    CPU_BUDGET: Final = 17290
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

    def __init__(self, builder: Builder) -> None:
        self.builder = builder
        self.last_fail_reason: str = ""
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
        self._dist: list[int] = [INF] * MAX_N
        self._dist_reset: Final[tuple[int, ...]] = (INF,) * MAX_N
        self._finished = True
        self._target: Position | None = None

    def search(
        self,
        ct: Controller,
        start: Position,
        target: Position,
        resource: ResourceType = ResourceType.TITANIUM,
    ) -> list[Position] | None:
        si = start.y * MAX_WIDTH + start.x
        gi = target.y * MAX_WIDTH + target.x

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
        sx = start.x
        sy = start.y

        if dist[gi] is INF:
            dist[gi] = 0

        # nb_count must exceed the largest possible f-value delta from a
        # single transition or Dial's algorithm drops nodes: if a node is
        # inserted into bucket (K + delta) % nb_count where delta >= nb_count,
        # the mod-wraparound can make (K + delta) % nb_count < cur_f, and the
        # bucket gets cleared before the node is processed. Max transition
        # cost here is a bridge jump (1 + 9 = 10), so 1024 is plenty.
        nb_count = 1024
        gx, gy = target.x, target.y
        f0 = abs(gx - sx) + abs(gy - sy)
        bk: list[list[int]] = [[] for _ in range(nb_count)]
        bk[f0 % nb_count].append(gi)
        cur_f = f0
        emp = 0

        # CPU budget is absolute turn-elapsed (not relative to A*'s own start).
        # Works now that update() is O(transport network) not O(map area);
        # on typical turns A* has ~900us here, on worst-case ~200us.
        found = False
        while emp < nb_count:
            bucket = bk[cur_f % nb_count]
            if not bucket:
                cur_f += 1
                emp += 1
                continue
            emp = 0
            for node_i in bucket:
                ny_, nx_ = divmod(node_i, MAX_WIDTH)
                node_h = abs(nx_ - sx) + abs(ny_ - sy)
                if dist[node_i] + node_h != cur_f:
                    continue
                if node_i == si:
                    found = True
                    break
                if ct.get_cpu_time_elapsed() > AStarSearch.CPU_BUDGET:
                    self._finished = False
                    self.last_fail_reason = "cpu_budget"
                    return None
                gn = dist[node_i]
                for ni, extra in neighbors[node_i]:
                    # Target tile is always allowed to be expanded into even
                    # if not currently routable (we only need to terminate
                    # there, not lay a conveyor on it).
                    if ni != gi:
                        if cost_grid[ni] is INF:
                            continue
                        if not routable[ni]:
                            continue
                    nd = gn + 1 + extra
                    if nd >= dist[ni]:
                        continue
                    dist[ni] = nd
                    ny2, nx2 = divmod(ni, MAX_WIDTH)
                    h_val = abs(nx2 - sx) + abs(ny2 - sy)
                    bk[(nd + h_val) % nb_count].append(ni)
            if found:
                break
            bk[cur_f % nb_count] = []
            cur_f += 1

        self._finished = True
        if not found:
            self.last_fail_reason = "exhausted"
            return None

        path: list[int] = [si]
        node = si
        cur_d = dist[si]
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
                if ni != gi and (cost_grid[ni] is INF or not routable[ni]):
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
        return [Position(i % MAX_WIDTH, i // MAX_WIDTH) for i in path]

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
