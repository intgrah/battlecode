"""Capacity-aware A* for conveyor chain routing.

Based on v50 FlowAstar neighbor expansion logic. Key differences:
- No flow simulation or leakage mask
- Goals = connected transport filtered by per-branch capacity
- Heuristic = Manhattan distance to core center
- Unseen tiles (env is None) are impassable — builders must explore first

Routes from harvester to the nearest connected transport tile with
spare capacity, using conveyors (cardinal, cost 3) and bridges
(r^2 <= 9, cost 30).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from astar import Astar
from building import (
    BuildingArmouredConveyor,
    BuildingBarrier,
    BuildingBridge,
    BuildingConveyor,
    BuildingCore,
    BuildingFoundry,
    BuildingHarvester,
    BuildingMarker,
    BuildingRoad,
    BuildingSplitter,
)
from cambc import Environment
from util import BRIDGE_DELTAS, DIR4_DELTA

if TYPE_CHECKING:
    from state import State

COST_REUSE = 0
COST_CONV = 3
COST_BRIDGE = 20
COST_ROAD_REPLACE = 3

_IMPASSABLE_ENV = frozenset(
    (Environment.WALL, Environment.ORE_TITANIUM, Environment.ORE_AXIONITE),
)

_TRANSPORT_CHECK = (
    BuildingConveyor, BuildingArmouredConveyor, BuildingSplitter, BuildingBridge,
)


def _tile_cost(env: list, ni: int, base_cost: int) -> tuple[bool, int]:
    """Check if tile is routable and return cost. Returns (passable, cost)."""
    ne = env[ni]
    if ne is None:
        return True, base_cost  # unseen — treat as buildable, recompute if wall
    if ne in _IMPASSABLE_ENV:
        return False, 0
    return True, base_cost




class ChainAstar(Astar[int]):
    """Route conveyor chain from harvester to connected transport network.

    Goals are pre-filtered by capacity (only tiles with spare branch capacity).
    Unseen tiles are penalized (COST_UNSEEN) but not blocked.
    """

    def __init__(
        self,
        state: State,
        sx: int,
        sy: int,
        goals: set[int],
        bottleneck: dict[int, int] | None = None,
        capacity: int = 4,
    ) -> None:
        self._w = state.w
        self._h = state.h
        self._gx = state.core_pos.x
        self._gy = state.core_pos.y
        self._env = state.env
        self._building = state.building
        self._my_team = state.my_team
        self._bottleneck = bottleneck or {}
        self._capacity = capacity
        si = sy * self._w + sx
        super().__init__(si, goals)

    def heuristic(self, node: int) -> int:
        return abs(node % self._w - self._gx) + abs(node // self._w - self._gy)

    def get_neighbors(self, node: int) -> list[tuple[int, int]]:
        w, h = self._w, self._h
        env = self._env
        building = self._building
        my_team = self._my_team

        e = env[node]
        bld = building[node]
        # Hard block: walls and ore (except harvester/foundry on ore)
        if e is not None and e in _IMPASSABLE_ENV:
            if not isinstance(bld, (BuildingHarvester, BuildingFoundry)):
                return []
        # Hard block: enemy buildings (except markers)
        if bld is not None and bld.team != my_team:
            if not isinstance(bld, BuildingMarker):
                return []

        cx, cy = node % w, node // w
        result: list[tuple[int, int]] = []
        bottleneck = self._bottleneck
        capacity = self._capacity
        node_overloaded = bottleneck.get(node, 0) >= capacity

        def _add_neighbor(ni: int, base_cost: int) -> None:
            ok, cost = _tile_cost(env, ni, base_cost)
            if not ok:
                return
            # Don't route INTO overloaded transport — new conveyor would feed
            # into an already-saturated chain
            if bottleneck.get(ni, 0) >= capacity:
                nbld = building[ni]
                if isinstance(nbld, _TRANSPORT_CHECK) and nbld.team == my_team:
                    return
            result.append((ni, cost))

        match bld:
            case BuildingCore():
                for ddx, ddy in DIR4_DELTA:
                    nx, ny = cx + ddx, cy + ddy
                    if 0 <= nx < w and 0 <= ny < h:
                        _add_neighbor(ny * w + nx, 0)

            case BuildingHarvester() | BuildingFoundry():
                for ddx, ddy in DIR4_DELTA:
                    nx, ny = cx + ddx, cy + ddy
                    if 0 <= nx < w and 0 <= ny < h:
                        _add_neighbor(ny * w + nx, 0)

            case BuildingBridge(target=bt):
                if bld.team == my_team:
                    if node_overloaded:
                        return []
                    bx, by = bt.x, bt.y
                    if 0 <= bx < w and 0 <= by < h:
                        _add_neighbor(by * w + bx, COST_REUSE)

            case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
                if bld.team == my_team:
                    if node_overloaded:
                        return []
                    ddx, ddy = d.delta()
                    nx, ny = cx + ddx, cy + ddy
                    if 0 <= nx < w and 0 <= ny < h:
                        _add_neighbor(ny * w + nx, COST_REUSE)

            case BuildingSplitter(direction=d):
                if bld.team == my_team:
                    if node_overloaded:
                        return []
                    ddx, ddy = d.delta()
                    for odx, ody in [(ddx, ddy), (-ddy, ddx), (ddy, -ddx)]:
                        nx, ny = cx + odx, cy + ody
                        if 0 <= nx < w and 0 <= ny < h:
                            _add_neighbor(ny * w + nx, COST_REUSE)

            case BuildingRoad():
                for ddx, ddy in DIR4_DELTA:
                    nx, ny = cx + ddx, cy + ddy
                    if 0 <= nx < w and 0 <= ny < h:
                        _add_neighbor(ny * w + nx, COST_ROAD_REPLACE)
                for ddx, ddy in BRIDGE_DELTAS:
                    nx, ny = cx + ddx, cy + ddy
                    if 0 <= nx < w and 0 <= ny < h:
                        _add_neighbor(ny * w + nx, COST_BRIDGE)

            case None | BuildingMarker():
                for ddx, ddy in DIR4_DELTA:
                    nx, ny = cx + ddx, cy + ddy
                    if 0 <= nx < w and 0 <= ny < h:
                        _add_neighbor(ny * w + nx, COST_CONV)
                for ddx, ddy in BRIDGE_DELTAS:
                    nx, ny = cx + ddx, cy + ddy
                    if 0 <= nx < w and 0 <= ny < h:
                        _add_neighbor(ny * w + nx, COST_BRIDGE)

        # Filter: don't route into enemy buildings or friendly harvesters/barriers
        filtered: list[tuple[int, int]] = []
        for ni, c in result:
            nbld = building[ni]
            if nbld is not None:
                if nbld.team != my_team and not isinstance(nbld, BuildingMarker):
                    continue
                if isinstance(nbld, (BuildingHarvester, BuildingBarrier)):
                    continue
                if isinstance(nbld, BuildingSplitter) and nbld.team == my_team:
                    # Only accept from back direction
                    sdx, sdy = nbld.direction.delta()
                    back_x = ni % w - sdx
                    back_y = ni // w - sdy
                    if (back_x, back_y) != (cx, cy):
                        continue
            filtered.append((ni, c))
        return filtered
