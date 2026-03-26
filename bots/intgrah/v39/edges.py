"""Edge definitions for D* Lite pathfinding.

Each EdgeDef defines the graph structure for a specific use case.
The D* Lite algorithm is graph-agnostic — it only needs successors,
predecessors, and a heuristic.
"""

from cambc import EntityType, Environment
from map_belief import (
    _TRANSPORT,
    COST_IMPASSABLE,
    COST_ROAD,
    MapBelief,
)

_WALK_8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
_CARDINAL = [(-1, 0), (1, 0), (0, -1), (0, 1)]

COST_CONV = 3
COST_BRIDGE = 10

_BRIDGE_DELTAS = [
    (dx, dy)
    for dx in range(-3, 4)
    for dy in range(-3, 4)
    if 0 < dx * dx + dy * dy <= 9 and abs(dx) + abs(dy) != 1
]


def _chebyshev(ax: int, ay: int, bx: int, by: int) -> int:
    dx = abs(ax - bx)
    dy = abs(ay - by)
    return max(dx, dy)


class RoadEdges:
    """8-directional builder movement on walkable tiles.

    Cost = walkability weight from MapBelief. Roads/conveyors are cheap,
    empty tiles cost more (must build a road), walls are impassable.
    """

    def successors(
        self,
        belief: MapBelief,
        x: int,
        y: int,
    ) -> list[tuple[int, int, int]]:
        result: list[tuple[int, int, int]] = []
        for dx, dy in _WALK_8:
            nx, ny = x + dx, y + dy
            if not belief.in_bounds(nx, ny):
                continue
            c = belief.walkable(nx, ny)
            if c < COST_IMPASSABLE:
                result.append((nx, ny, c))
        return result

    def predecessors(
        self,
        belief: MapBelief,
        x: int,
        y: int,
    ) -> list[tuple[int, int, int]]:
        return self.successors(belief, x, y)

    def heuristic(self, ax: int, ay: int, bx: int, by: int) -> int:
        return _chebyshev(ax, ay, bx, by) * COST_ROAD


class FlowEdges:
    """Cardinal conveyors + bridge jumps for resource chain planning.

    Directed graph: conveyors output in one direction only.
    Existing transport with flow < 1.0 = cost 0 (reuse).
    Existing transport at capacity = impassable (reroute).
    Empty buildable tile = cost of building (conveyor or bridge).
    """

    def successors(
        self,
        belief: MapBelief,
        x: int,
        y: int,
    ) -> list[tuple[int, int, int]]:
        result: list[tuple[int, int, int]] = []
        i = belief.idx(x, y)
        ent = belief.entity[i]

        if ent is not None:
            etype, team = ent
            if team == belief.my_team and (
                etype in _TRANSPORT or etype == EntityType.CORE
            ):
                flow = belief.flow_in[i]
                reuse_cost = 1 if flow < 1.0 else COST_IMPASSABLE
                d = belief.direction[i]
                bt = belief.bridge_target[i]
                if d is not None:
                    dx, dy = d.delta()
                    nx, ny = x + dx, y + dy
                    if belief.in_bounds(nx, ny):
                        result.append((nx, ny, reuse_cost))
                elif bt is not None:
                    bx, by = bt
                    if belief.in_bounds(bx, by):
                        result.append((bx, by, reuse_cost))
                return result

        for dx, dy in _CARDINAL:
            nx, ny = x + dx, y + dy
            if not belief.in_bounds(nx, ny):
                continue
            c = self._flow_cost(belief, nx, ny, is_bridge=False)
            if c < COST_IMPASSABLE:
                result.append((nx, ny, c))

        for dx, dy in _BRIDGE_DELTAS:
            nx, ny = x + dx, y + dy
            if not belief.in_bounds(nx, ny):
                continue
            c = self._flow_cost(belief, nx, ny, is_bridge=True)
            if c < COST_IMPASSABLE:
                result.append((nx, ny, c))

        return result

    def predecessors(
        self,
        belief: MapBelief,
        x: int,
        y: int,
    ) -> list[tuple[int, int, int]]:
        result: list[tuple[int, int, int]] = []

        for dx, dy in _CARDINAL:
            nx, ny = x + dx, y + dy
            if not belief.in_bounds(nx, ny):
                continue
            ni = belief.idx(nx, ny)
            ent = belief.entity[ni]
            if ent is not None:
                etype, team = ent
                if team == belief.my_team:
                    flow = belief.flow_in[ni]
                    reuse_cost = 1 if flow < 1.0 else COST_IMPASSABLE
                    if etype == EntityType.HARVESTER:
                        result.append((nx, ny, reuse_cost))
                        continue
                    if etype in _TRANSPORT:
                        d = belief.direction[ni]
                        if d is not None:
                            ddx, ddy = d.delta()
                            if nx + ddx == x and ny + ddy == y:
                                result.append((nx, ny, reuse_cost))
                        continue

            c = self._flow_cost(belief, nx, ny, is_bridge=False)
            if c < COST_IMPASSABLE:
                result.append((nx, ny, c))

        for dx, dy in _BRIDGE_DELTAS:
            nx, ny = x + dx, y + dy
            if not belief.in_bounds(nx, ny):
                continue
            ni = belief.idx(nx, ny)
            ent = belief.entity[ni]
            if ent is not None:
                etype, team = ent
                if team == belief.my_team and etype == EntityType.BRIDGE:
                    flow = belief.flow_in[ni]
                    reuse_cost = 1 if flow < 1.0 else COST_IMPASSABLE
                    bt = belief.bridge_target[ni]
                    if bt is not None and bt[0] == x and bt[1] == y:
                        result.append((nx, ny, reuse_cost))
                        continue

            c = self._flow_cost(belief, nx, ny, is_bridge=True)
            if c < COST_IMPASSABLE:
                result.append((nx, ny, c))

        return result

    def heuristic(self, ax: int, ay: int, bx: int, by: int) -> int:
        dx = abs(ax - bx)
        dy = abs(ay - by)
        return max(dx, dy)

    def _flow_cost(self, belief: MapBelief, x: int, y: int, *, is_bridge: bool) -> int:
        i = belief.idx(x, y)
        env = belief.env[i]
        if env is None:
            return COST_BRIDGE if is_bridge else COST_CONV

        if env in (
            Environment.WALL,
            Environment.ORE_TITANIUM,
            Environment.ORE_AXIONITE,
        ):
            return COST_IMPASSABLE
        ent = belief.entity[i]
        if ent is None:
            return COST_BRIDGE if is_bridge else COST_CONV
        etype, team = ent
        if team != belief.my_team:
            return COST_IMPASSABLE
        if etype in _TRANSPORT or etype == EntityType.CORE:
            if belief.flow_in[i] >= 1.0:
                return COST_IMPASSABLE
            return 1
        if etype == EntityType.ROAD:
            return COST_BRIDGE if is_bridge else COST_CONV
        return COST_IMPASSABLE
