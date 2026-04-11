from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingFoundry,
    BuildingHarvester,
    BuildingRoad,
    BuildingSplitter,
)
from cambc import Controller, Environment, Position
from util import DIR4, DIR8, INF

from builder.helpers import find_dangling, is_dangling, ore_available, pick_ore_target

if TYPE_CHECKING:
    from builder.state import State

_FLOW_PENALTY = (0, 0, 0, 0, 1, 3, 10, 50, 500)


def can_place_junction(state: State, ct: Controller, pos: Position) -> bool:
    match state.get_building(pos):
        case None:
            pass
        case BuildingConveyor(team=t) | BuildingRoad(team=t) if t == ct.get_team():
            pass
        case _:
            return False

    conveyors = state.get_conveyors_to_here(pos)
    adjacent_conveyors = [c for c in conveyors if c.distance_squared(pos) <= 2]
    if len(adjacent_conveyors) > 1 or len(conveyors) < 1:
        return False
    buildable_count = 0
    for d in DIR4:
        new_pos = pos.add(d)
        if state.get_env(new_pos) != Environment.EMPTY:
            continue
        match state.get_building(new_pos):
            case None:
                buildable_count += 1
            case BuildingConveyor() | BuildingBridge() | BuildingSplitter():
                pass
            case b if b.team == ct.get_team():
                buildable_count += 1

    return buildable_count >= 1


def update_map_econ(state: State, ct: Controller) -> None:
    w = state.w
    state.adjacent_to_unconnected_harvester = {
        p for p in state.adjacent_to_unconnected_harvester if not ct.is_in_vision(p)
    }
    state.adjacent_to_unconnected_foundry = {
        p for p in state.adjacent_to_unconnected_foundry if not ct.is_in_vision(p)
    }
    state.adjacent_to_harvester = {
        p for p in state.adjacent_to_harvester if not ct.is_in_vision(p)
    }
    my_team = ct.get_team()
    for pos in state.nearby_positions:
        i = pos.y * w + pos.x
        bld = state.get_building(pos)
        match bld:
            case BuildingHarvester():
                adjacent_conveyor = False
                for d in DIR4:
                    match state.get_building(pos.add(d)):
                        case (
                            BuildingConveyor(team=t)
                            | BuildingBridge(team=t)
                            | BuildingSplitter(team=t)
                            | BuildingArmouredConveyor(team=t)
                        ) if t == my_team:
                            adjacent_conveyor = True
                            break
                if not adjacent_conveyor:
                    for d in DIR4:
                        state.adjacent_to_unconnected_harvester.add(pos.add(d))
                for d in DIR4:
                    state.adjacent_to_harvester.add(pos.add(d))
            case BuildingFoundry(team=t) if t == my_team:
                adjacent_conveyor = False
                for d in DIR4:
                    match state.get_building(pos.add(d)):
                        case (
                            BuildingConveyor(team=t2)
                            | BuildingBridge(team=t2)
                            | BuildingArmouredConveyor(team=t2)
                        ) if t2 == my_team:
                            adjacent_conveyor = True
                            break
                if not adjacent_conveyor:
                    for d in DIR4:
                        state.adjacent_to_unconnected_foundry.add(pos.add(d))
        if pos in state.adjacent_to_enemy_launcher:
            state.nav_cost[i] = INF

        match bld:
            case (
                BuildingConveyor(team=t)
                | BuildingArmouredConveyor(team=t)
                | BuildingSplitter(team=t)
                | BuildingBridge(team=t)
            ) if t == ct.get_team():
                fh = state.flow_history[i]
                occupied = sum((fh >> s) & 0b11 != 0 for s in range(0, 16, 2))
                state.conveyor_cost_grid[i] += _FLOW_PENALTY[occupied]

    my_position = ct.get_position()
    if state.nearest_junction_site and not can_place_junction(
        state, ct, state.nearest_junction_site
    ):
        state.nearest_junction_site = None
    for pos in state.nearby_positions:
        if (
            state.nearest_junction_site is None
            or (
                state.nearest_junction_site.distance_squared(my_position)
                < pos.distance_squared(my_position)
            )
        ) and can_place_junction(state, ct, pos):
            state.nearest_junction_site = pos


def update_dangling(state: State, ct: Controller) -> None:
    my_pos = ct.get_position()
    if is_dangling(state, ct, my_pos):
        state.dangling_output = my_pos
    else:
        match state.get_building(my_pos):
            case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
                target = my_pos.add(d)
                if is_dangling(state, ct, target):
                    state.dangling_output = target
            case _:
                for d in DIR8:
                    n = my_pos.add(d)
                    if is_dangling(state, ct, n):
                        state.dangling_output = n
                        break
    if state.pending_bridge:
        state.dangling_output = state.pending_bridge
    elif state.dangling_output is None or not is_dangling(
        state, ct, state.dangling_output
    ):
        state.dangling_output = find_dangling(state, ct)


def update_ore_target(state: State, ct: Controller) -> None:
    my_pos = ct.get_position()
    candidate_ore = pick_ore_target(state, ct)
    if (
        not state.ore_target
        or not ore_available(state, ct, state.ore_target)
        or (
            candidate_ore
            and candidate_ore.distance_squared(my_pos) <= 2
            and state.ore_target.distance_squared(my_pos) > 2
        )
    ):
        state.ore_target = candidate_ore
