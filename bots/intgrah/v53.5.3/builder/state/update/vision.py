from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingFoundry,
    BuildingLauncher,
    BuildingSplitter,
    make_building,
)
from cambc import Controller, ResourceType
from util import DIR8

if TYPE_CHECKING:
    from builder.state import State


def prune_stale(state: State, ct: Controller) -> None:
    state.healable_buildings = [
        p for p in state.healable_buildings if not ct.is_in_vision(p)
    ]
    state.adjacent_to_enemy_launcher = {
        p for p in state.adjacent_to_enemy_launcher if not ct.is_in_vision(p)
    }
    for pos in ct.get_nearby_tiles():
        i = state.idx(pos)
        state.conveyors_to_here[i] = [
            p for p in state.conveyors_to_here[i] if not ct.is_in_vision(p)
        ]
        state.splitters_to_here[i] = [
            p for p in state.splitters_to_here[i] if not ct.is_in_vision(p)
        ]


def update_vision(state: State, ct: Controller) -> None:
    rnd = ct.get_current_round()
    state.nearby_buildings = []

    for pos in ct.get_nearby_tiles():
        i = state.idx(pos)
        state.env[i] = ct.get_tile_env(pos)
        bid = ct.get_tile_building_id(pos)
        if bid is None:
            state.buildings[i] = None
            continue
        state.buildings[i] = b = make_building(ct, bid, ct.get_entity_type(bid))
        state.hp[i] = ct.get_hp(bid)
        state.max_hp[i] = ct.get_max_hp(bid)

        match b:
            case (
                BuildingConveyor()
                | BuildingArmouredConveyor()
                | BuildingBridge()
                | BuildingSplitter()
                | BuildingFoundry()
            ):
                match ct.get_stored_resource(bid):
                    case None:
                        code = 0
                    case ResourceType.TITANIUM:
                        code = 1
                    case ResourceType.RAW_AXIONITE:
                        code = 2
                    case ResourceType.REFINED_AXIONITE:
                        code = 3
                shift = (rnd >> 3) << 1
                state.flow_history[i] = (state.flow_history[i] & ~(0b11 << shift)) | (
                    code << shift
                )

        match b:
            case BuildingConveyor(direction=d):
                target = pos.add(d)
                if state.in_bounds(target):
                    state.conveyors_to_here[state.idx(target)].append(pos)
            case BuildingBridge(target=t):
                state.conveyors_to_here[state.idx(t)].append(pos)
            case BuildingSplitter(direction=d):
                for sd in [
                    d,
                    d.rotate_right().rotate_right(),
                    d.rotate_left().rotate_left(),
                ]:
                    target = pos.add(sd)
                    if state.in_bounds(target):
                        state.splitters_to_here[state.idx(target)].append(pos)

        state.nearby_buildings.append(pos)
        if state.hp[i] < state.max_hp[i] and b is not None and b.team == ct.get_team():
            state.healable_buildings.append(pos)
        match b:
            case BuildingLauncher(team=t) if t != state.my_team:
                for d in DIR8:
                    state.adjacent_to_enemy_launcher.add(pos.add(d))
