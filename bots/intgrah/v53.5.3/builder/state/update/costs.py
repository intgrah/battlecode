from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingCore,
    BuildingGunner,
    BuildingRoad,
    BuildingSentinel,
    BuildingSplitter,
)
from cambc import Controller, Environment
from util import INF, ROAD_COST

if TYPE_CHECKING:
    from builder.state import State


def update_costs(state: State, ct: Controller) -> None:
    w = state.w
    for pos in state.nearby_positions:
        if 0 <= pos.x < state.w and 0 <= pos.y < state.h:
            i = pos.y * w + pos.x
            terrain = state.env[i]
            bld = state.buildings[i]
            if terrain == Environment.WALL:
                cost = INF
                conveyor_cost = INF
            elif bld is not None:
                match bld:
                    case (
                        BuildingConveyor()
                        | BuildingRoad()
                        | BuildingSplitter()
                        | BuildingArmouredConveyor()
                        | BuildingBridge()
                    ):
                        cost = 2
                        conveyor_cost = 1
                    case BuildingCore(team=t) if t == ct.get_team():
                        cost = 2
                        conveyor_cost = 1
                    case _:
                        cost = INF
                        conveyor_cost = INF
            elif terrain in (
                Environment.EMPTY,
                Environment.ORE_TITANIUM,
                Environment.ORE_AXIONITE,
            ):
                cost = ROAD_COST
                conveyor_cost = 1 if terrain == Environment.EMPTY else 50
            else:
                cost = 2
                conveyor_cost = 1
            state.nav_cost[i] = cost
            state.conveyor_cost_grid[i] = conveyor_cost


def update_enemy_turrets(state: State, ct: Controller) -> None:
    w = state.w
    my_pos = ct.get_position()

    if state.nearest_enemy_turret:
        i = state.nearest_enemy_turret.y * w + state.nearest_enemy_turret.x
        match state.buildings[i]:
            case BuildingGunner(team=t) | BuildingSentinel(team=t) if (
                t != ct.get_team()
            ):
                pass
            case _:
                state.nearest_enemy_turret = None

    min_dist = INF
    for pos in state.nearby_positions:
        match state.buildings[pos.y * w + pos.x]:
            case BuildingGunner(team=t) | BuildingSentinel(team=t) if (
                t != ct.get_team()
            ):
                dist = (pos.x - my_pos.x) ** 2 + (pos.y - my_pos.y) ** 2
                if dist < min_dist:
                    min_dist = dist
                    state.nearest_enemy_turret = pos
