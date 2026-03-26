"""Flow graph: Ramalingam-Reps SSSP from core through the flow network.

Edges model how flow can move from tile A toward the core:
  - Existing transport at A pointing at B: cost COST_REUSE (free reuse)
  - Empty/road/unseen A, cardinal neighbor B: cost COST_CONV (build conveyor)
  - Empty/road/unseen A, bridge-range B: cost COST_BRIDGE (build bridge)
  - Transport at A pointing elsewhere: NO edge (locked direction)
  - Core tile: cost 0 to cardinal neighbors

In the SP graph edges are reversed: core is source, dist[v] = cost to connect v
to core. Existing transport creates cheap edges that Dijkstra naturally prefers.

Blocked tiles (congested subtree) are completely removed from the graph.
"""

from algorithms.ramalingam_reps import INF, RamalingamReps
from builder.state import State
from cambc import EntityType, Environment
from util import DIR4_DELTA, TRANSPORT

_BRIDGE_DELTAS = [
    (dx, dy)
    for dx in range(-3, 4)
    for dy in range(-3, 4)
    if 0 < dx * dx + dy * dy <= 9 and abs(dx) + abs(dy) != 1
]

COST_REUSE = 1
COST_CONV = 3
COST_BRIDGE = 10
COST_ROAD_REPLACE = 3


class FlowGraph:
    def __init__(self, state: State) -> None:
        self.state = state
        n = state.w * state.h
        self.sp = RamalingamReps(n)
        self._out_edges: list[dict[int, int]] = [{} for _ in range(n)]

    def initialize(self, core_x: int, core_y: int) -> None:
        b = self.state
        for y in range(b.h):
            for x in range(b.w):
                fi = b.idx(x, y)
                targets = self._compute_targets(x, y, fi)
                self._out_edges[fi] = targets
                for ti, cost in targets.items():
                    self.sp.adj[ti].append((fi, cost))
                    self.sp.inv[fi].append(ti)

        core_tiles = []
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                cx, cy = core_x + dx, core_y + dy
                if b.in_bounds(cx, cy):
                    core_tiles.append(b.idx(cx, cy))
        self.sp.set_sources(core_tiles)

    def on_tile_changed(self, x: int, y: int) -> None:
        b = self.state
        self._rebuild_node(x, y)
        for dx, dy in DIR4_DELTA:
            nx, ny = x + dx, y + dy
            if b.in_bounds(nx, ny):
                self._rebuild_node(nx, ny)
        for dx, dy in _BRIDGE_DELTAS:
            nx, ny = x + dx, y + dy
            if b.in_bounds(nx, ny):
                self._sync_edge(nx, ny, x, y)
        self.sp.propagate()

    def _rebuild_node(self, x: int, y: int) -> None:
        b = self.state
        fi = b.idx(x, y)

        new_map = self._compute_targets(x, y, fi)

        old_map = self._out_edges[fi]

        for ti in list(old_map):
            if ti not in new_map:
                del old_map[ti]
                self.sp.remove_edge(ti, fi)

        for ti, cost in new_map.items():
            old_cost = old_map.get(ti)
            if old_cost is None:
                old_map[ti] = cost
                self.sp.add_edge(ti, fi, cost)
            elif old_cost != cost:
                old_map[ti] = cost
                self.sp.update_edge(ti, fi, old_cost, cost)

    def _sync_edge(self, fx: int, fy: int, tx: int, ty: int) -> None:
        b = self.state
        fi = b.idx(fx, fy)
        ti = b.idx(tx, ty)

        cost = self._single_edge_cost(fx, fy, tx, ty, fi, ti)

        old_map = self._out_edges[fi]
        old_cost = old_map.get(ti)
        if old_cost is None and cost < INF:
            old_map[ti] = cost
            self.sp.add_edge(ti, fi, cost)
        elif old_cost is not None and cost >= INF:
            del old_map[ti]
            self.sp.remove_edge(ti, fi)
        elif old_cost is not None and cost != old_cost:
            old_map[ti] = cost
            self.sp.update_edge(ti, fi, old_cost, cost)

    def _compute_targets(self, x: int, y: int, fi: int) -> dict[int, int]:
        b = self.state

        if b.my_flow.blocked[fi] or self._is_impassable(fi):
            return {}

        ent = b.entity[fi]
        if ent is not None:
            etype, team = ent
            if team != b.my_team:
                return {}

            if etype == EntityType.CORE:
                result: dict[int, int] = {}
                for dx, dy in DIR4_DELTA:
                    nx, ny = x + dx, y + dy
                    if b.in_bounds(nx, ny):
                        ti = b.idx(nx, ny)
                        if not b.my_flow.blocked[ti] and not self._is_impassable(ti):
                            result[ti] = 0
                return result

            if etype in TRANSPORT:
                return self._transport_targets(x, y, fi, etype)

            if etype == EntityType.ROAD:
                return self._buildable_targets(x, y)

            return {}

        return self._buildable_targets(x, y)

    def _transport_targets(
        self,
        x: int,
        y: int,
        fi: int,
        etype: EntityType,
    ) -> dict[int, int]:
        b = self.state
        d = b.direction[fi]
        bt = b.bridge_target[fi]

        if etype == EntityType.BRIDGE and bt is not None:
            bx, by = bt
            if b.in_bounds(bx, by):
                ti = b.idx(bx, by)
                if not b.my_flow.blocked[ti] and not self._is_impassable(ti):
                    return {ti: COST_REUSE}
            return {}

        if d is not None:
            dx, dy = d.delta()
            nx, ny = x + dx, y + dy
            if b.in_bounds(nx, ny):
                ti = b.idx(nx, ny)
                if not b.my_flow.blocked[ti] and not self._is_impassable(ti):
                    return {ti: COST_REUSE}
            return {}

        return {}

    def _buildable_targets(self, x: int, y: int) -> dict[int, int]:
        b = self.state
        result: dict[int, int] = {}
        for dx, dy in DIR4_DELTA:
            nx, ny = x + dx, y + dy
            if b.in_bounds(nx, ny):
                ti = b.idx(nx, ny)
                if not b.my_flow.blocked[ti] and not self._is_impassable(ti):
                    result[ti] = COST_CONV
        for dx, dy in _BRIDGE_DELTAS:
            nx, ny = x + dx, y + dy
            if b.in_bounds(nx, ny):
                ti = b.idx(nx, ny)
                if not b.my_flow.blocked[ti] and not self._is_impassable(ti):
                    result[ti] = COST_BRIDGE
        return result

    def _single_edge_cost(
        self,
        fx: int,
        fy: int,
        tx: int,
        ty: int,
        fi: int,
        ti: int,
    ) -> int:
        b = self.state
        if b.my_flow.blocked[fi] or b.my_flow.blocked[ti]:
            return INF
        if self._is_impassable(fi) or self._is_impassable(ti):
            return INF

        ent = b.entity[fi]
        is_bridge = abs(fx - tx) + abs(fy - ty) != 1

        if ent is not None:
            etype, team = ent
            if team != b.my_team:
                return INF
            if etype == EntityType.BRIDGE:
                bt = b.bridge_target[fi]
                if bt == (tx, ty):
                    return COST_REUSE
                return INF
            if etype in TRANSPORT:
                d = b.direction[fi]
                if d is not None:
                    dx, dy = d.delta()
                    if fx + dx == tx and fy + dy == ty:
                        return COST_REUSE
                return INF
            if etype == EntityType.CORE:
                return 0
            if etype == EntityType.ROAD:
                return COST_BRIDGE if is_bridge else COST_ROAD_REPLACE
            return INF

        return COST_BRIDGE if is_bridge else COST_CONV

    def _is_impassable(self, i: int) -> bool:
        b = self.state
        env = b.env[i]
        if env is not None and env in (
            Environment.WALL,
            Environment.ORE_TITANIUM,
            Environment.ORE_AXIONITE,
        ):
            return True
        ent = b.entity[i]
        return bool(ent is not None and ent[1] != b.my_team)

    def dist(self, x: int, y: int) -> int:
        return self.sp.dist[self.state.idx(x, y)]

    def get_path_from(self, x: int, y: int) -> list[tuple[int, int]] | None:
        idx_path = self.sp.get_path(self.state.idx(x, y))
        if idx_path is None:
            return None
        b = self.state
        path = [(i % b.w, i // b.w) for i in idx_path]
        path.reverse()
        return path
