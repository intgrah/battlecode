"""Capacity-aware A* for conveyor chain routing.

Based on v50 FlowAstar neighbor expansion logic. Key differences:
- No flow simulation or leakage mask
- Goals = connected transport filtered by per-branch capacity
- Heuristic = Manhattan distance to core center
- Unseen tiles (env is None) are impassable — builders must explore first

Routes from harvester to the nearest connected transport tile with
spare capacity, using conveyors (cardinal, cost 3) and bridges
(r^2 <= 9, cost 20).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from astar import Astar
from building import (
    BuildingArmouredConveyor,
    BuildingBarrier,
    BuildingBreach,
    BuildingBridge,
    BuildingConveyor,
    BuildingCore,
    BuildingFoundry,
    BuildingGunner,
    BuildingHarvester,
    BuildingLauncher,
    BuildingMarker,
    BuildingRoad,
    BuildingSentinel,
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

# Penalty costs for routing through enemy buildings (attack chains)
COST_ENEMY_ROAD = 4
COST_ENEMY_CONV = 12
COST_ENEMY_BARRIER = 20
COST_FLOW_DANGER = 10

_IMPASSABLE_ENV = frozenset((Environment.WALL,))

_TRANSPORT_CHECK = (
    BuildingConveyor,
    BuildingArmouredConveyor,
    BuildingSplitter,
    BuildingBridge,
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
        self._danger = state.danger_zones
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

        danger = self._danger

        def _add_neighbor(ni: int, base_cost: int) -> None:
            ok, cost = _tile_cost(env, ni, base_cost)
            if not ok:
                return
            # Danger zones: heavy penalty (builder has to walk there)
            if ni in danger:
                cost += COST_FLOW_DANGER
            # Don't route INTO overloaded transport
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
                elif isinstance(nbld, (BuildingHarvester, BuildingBarrier)):
                    continue
                elif isinstance(nbld, BuildingSplitter) and nbld.team == my_team:
                    # Only accept from back direction
                    sdx, sdy = nbld.direction.delta()
                    back_x = ni % w - sdx
                    back_y = ni // w - sdy
                    if (back_x, back_y) != (cx, cy):
                        continue
            filtered.append((ni, c))
        return filtered


class AttackAstar(Astar[int]):
    """Route fresh conveyor chain for attack — NO reuse of existing transport.

    Every tile gets COST_CONV (cardinal) or COST_BRIDGE (bridge hop).
    Source is a Ti source tile (harvester free side or ore for new harvester).
    Goals are valid gunner positions near enemy buildings.
    Heuristic targets the centroid of the goal set.
    """

    def __init__(
        self,
        state: State,
        source: int,
        goals: set[int],
    ) -> None:
        self._w = state.w
        self._h = state.h
        self._env = state.env
        self._building = state.building
        self._my_team = state.my_team
        self._danger = state.danger_zones
        self._econ = state.connected_transport

        # Heuristic target: centroid of goals
        if goals:
            sx = sum(g % self._w for g in goals)
            sy = sum(g // self._w for g in goals)
            n = len(goals)
            self._hx = sx // n
            self._hy = sy // n
        else:
            self._hx = state.core_pos.x
            self._hy = state.core_pos.y

        super().__init__(source, goals)

    def heuristic(self, node: int) -> int:
        return abs(node % self._w - self._hx) + abs(node // self._w - self._hy)

    def get_neighbors(self, node: int) -> list[tuple[int, int]]:
        w, h = self._w, self._h
        env = self._env
        building = self._building
        my_team = self._my_team

        e = env[node]
        bld = building[node]
        # Hard block: walls and ore (except harvester on ore = our source)
        if (
            e is not None
            and e in _IMPASSABLE_ENV
            and not isinstance(bld, (BuildingHarvester, BuildingFoundry))
        ):
            return []
        # Hard block: connected econ transport — attack must NEVER route through
        if node in self._econ:
            return []
        # Hard block: enemy core/turrets/harvesters/foundry (truly impassable)
        # Allow routing through enemy roads/conveyors/barriers/splitters/bridges
        if (
            bld is not None
            and bld.team != my_team
            and isinstance(
                bld,
                (
                    BuildingCore,
                    BuildingHarvester,
                    BuildingFoundry,
                    BuildingGunner,
                    BuildingSentinel,
                    BuildingBreach,
                    BuildingLauncher,
                ),
            )
        ):
            return []

        cx, cy = node % w, node // w
        result: list[tuple[int, int]] = []
        danger = self._danger

        # Direction following: if our non-econ transport is here, only expand
        # in its actual output direction(s). Forces A* to follow existing chains.
        if (
            bld is not None
            and bld.team == my_team
            and isinstance(bld, _TRANSPORT_CHECK)
            and node not in self._econ
        ):
            out_tiles: list[tuple[int, int]] = []
            match bld:
                case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
                    ddx, ddy = d.delta()
                    out_tiles.append((cx + ddx, cy + ddy))
                case BuildingSplitter(direction=d):
                    ddx, ddy = d.delta()
                    for odx, ody in [(ddx, ddy), (-ddy, ddx), (ddy, -ddx)]:
                        out_tiles.append((cx + odx, cy + ody))
                case BuildingBridge(target=tgt):
                    out_tiles.append((tgt.x, tgt.y))
            for ox, oy in out_tiles:
                if 0 <= ox < w and 0 <= oy < h:
                    oi = oy * w + ox
                    oe = env[oi]
                    if oe is not None and oe in _IMPASSABLE_ENV:
                        continue
                    result.append((oi, COST_REUSE))
            return result  # ONLY output directions, no cardinal/bridge expansion

        # Harvesters: expand to all 4 cardinal neighbors (they output everywhere)
        if isinstance(bld, BuildingHarvester):
            for ddx, ddy in DIR4_DELTA:
                nx, ny = cx + ddx, cy + ddy
                if 0 <= nx < w and 0 <= ny < h:
                    ni = ny * w + nx
                    ne = env[ni]
                    if ne is not None and ne in _IMPASSABLE_ENV:
                        continue
                    result.append((ni, COST_REUSE))
            return result

        # Cardinal neighbors (COST_CONV each — always build new)
        for ddx, ddy in DIR4_DELTA:
            nx, ny = cx + ddx, cy + ddy
            if 0 <= nx < w and 0 <= ny < h:
                ni = ny * w + nx
                ne = env[ni]
                if ne is not None and ne in _IMPASSABLE_ENV:
                    continue
                cost = COST_CONV
                # Danger zones: penalty instead of hard block
                if ni in danger:
                    cost += COST_FLOW_DANGER
                result.append((ni, cost))

        # Bridge jumps (COST_BRIDGE each)
        # Skip bridge targets with enemy buildings — can't build bridge there
        for ddx, ddy in BRIDGE_DELTAS:
            nx, ny = cx + ddx, cy + ddy
            if 0 <= nx < w and 0 <= ny < h:
                ni = ny * w + nx
                ne = env[ni]
                if ne is not None and ne in _IMPASSABLE_ENV:
                    continue
                nbld = building[ni]
                if nbld is not None:
                    if isinstance(nbld, BuildingMarker):
                        pass  # markers are free
                    elif nbld.team != my_team:
                        continue  # can't bridge to enemy-occupied tile
                    elif isinstance(nbld, _TRANSPORT_CHECK):
                        continue  # don't bridge into our own transport
                    # own road/barrier OK
                if ni in danger:
                    continue  # never bridge into danger zones
                result.append((ni, COST_BRIDGE))

        # Filter: route through buildable tiles OR reuse own non-econ transport
        econ = self._econ
        filtered: list[tuple[int, int]] = []
        for ni, c in result:
            nbld = building[ni]
            if nbld is not None:
                if isinstance(nbld, BuildingMarker):
                    pass  # any team — can build over markers
                elif nbld.team == my_team and isinstance(
                    nbld, (BuildingRoad, BuildingBarrier)
                ):
                    pass  # own road/barrier — destroyable for attack
                elif (
                    nbld.team == my_team
                    and isinstance(nbld, _TRANSPORT_CHECK)
                    and ni not in econ
                ):
                    c = COST_REUSE  # strongly prefer existing attack chain
                elif nbld.team != my_team:
                    # Enemy buildings: penalty costs by type
                    if isinstance(nbld, BuildingRoad):
                        c += COST_ENEMY_ROAD
                    elif isinstance(
                        nbld,
                        (
                            BuildingConveyor,
                            BuildingArmouredConveyor,
                            BuildingSplitter,
                            BuildingBridge,
                        ),
                    ):
                        c += COST_ENEMY_CONV
                    elif isinstance(nbld, BuildingBarrier):
                        continue  # can't clear barriers inline
                    else:
                        # Core/turrets/harvesters/foundry — truly impassable
                        continue
                else:
                    continue
            filtered.append((ni, c))
        return filtered
