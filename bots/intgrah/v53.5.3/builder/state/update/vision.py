from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    ETYPE_BUILDING,
    Building,
    BuildingBridge,
    BuildingConveyor,
    BuildingLauncher,
    BuildingSplitter,
)
from cambc import Controller, EntityType, GameConstants, ResourceType
from util import DIR8

if TYPE_CHECKING:
    from builder.state import State


def _make_building(ct: Controller, bid: int, etype: EntityType) -> Building | None:
    team = ct.get_team(bid)
    match etype:
        case EntityType.CONVEYOR | EntityType.ARMOURED_CONVEYOR | EntityType.SPLITTER:
            cls = ETYPE_BUILDING[etype]
            return cls(team, ct.get_direction(bid))
        case EntityType.GUNNER | EntityType.SENTINEL | EntityType.BREACH:
            cls = ETYPE_BUILDING[etype]
            return cls(team, ct.get_direction(bid))
        case EntityType.BRIDGE:
            return BuildingBridge(team, ct.get_bridge_target(bid))
        case _:
            cls = ETYPE_BUILDING.get(etype)
            if cls is None:
                return None
            return cls(team)


def update_vision(state: State, ct: Controller) -> None:
    w = state.w
    nearby_positions = ct.get_nearby_tiles(GameConstants.BUILDER_BOT_VISION_RADIUS_SQ)
    state.nearby_positions = nearby_positions
    state.nearby_buildings = []

    state.healable_buildings = [
        p for p in state.healable_buildings if not ct.is_in_vision(p)
    ]
    state.adjacent_to_enemy_launcher = {
        p for p in state.adjacent_to_enemy_launcher if not ct.is_in_vision(p)
    }

    for pos in nearby_positions:
        if 0 <= pos.x < state.w and 0 <= pos.y < state.h:
            i = pos.y * w + pos.x
            state.conveyors_to_here[i] = [
                p for p in state.conveyors_to_here[i] if not ct.is_in_vision(p)
            ]
            state.splitters_to_here[i] = [
                p for p in state.splitters_to_here[i] if not ct.is_in_vision(p)
            ]

    for pos in nearby_positions:
        if 0 <= pos.x < state.w and 0 <= pos.y < state.h:
            i = pos.y * w + pos.x
            state.env[i] = ct.get_tile_env(pos)
            building_id = ct.get_tile_building_id(pos)
            if (
                building_id is not None
                and ct.get_entity_type(building_id) != EntityType.MARKER
            ):
                etype = ct.get_entity_type(building_id)
                bld = _make_building(ct, building_id, etype)
                state.buildings[i] = bld
                state.hp[i] = ct.get_hp(building_id)
                state.max_hp[i] = ct.get_max_hp(building_id)

                match bld:
                    case BuildingConveyor() | BuildingBridge() | BuildingSplitter():
                        res = ct.get_stored_resource(building_id)
                        slot = ct.get_current_round() % 8
                        shift = slot * 2
                        match res:
                            case None:
                                code = 0
                            case ResourceType.TITANIUM:
                                code = 1
                            case ResourceType.RAW_AXIONITE:
                                code = 2
                            case _:
                                code = 3
                        state.flow_history[i] = (
                            state.flow_history[i] & ~(3 << shift)
                        ) | (code << shift)

                match bld:
                    case BuildingConveyor(direction=d):
                        target_pos = pos.add(d)
                        if 0 <= target_pos.x < state.w and 0 <= target_pos.y < state.h:
                            ti = target_pos.y * w + target_pos.x
                            state.conveyors_to_here[ti].append(pos)
                    case BuildingBridge(target=t):
                        if 0 <= t.x < state.w and 0 <= t.y < state.h:
                            ti = t.y * w + t.x
                            state.conveyors_to_here[ti].append(pos)
                    case BuildingSplitter(direction=d):
                        for sd in [
                            d,
                            d.rotate_right().rotate_right(),
                            d.rotate_left().rotate_left(),
                        ]:
                            target_pos = pos.add(sd)
                            if (
                                0 <= target_pos.x < state.w
                                and 0 <= target_pos.y < state.h
                            ):
                                ti = target_pos.y * w + target_pos.x
                                state.splitters_to_here[ti].append(pos)

                state.nearby_buildings.append(pos)
                if (
                    state.hp[i] < state.max_hp[i]
                    and bld is not None
                    and bld.team == ct.get_team()
                ):
                    state.healable_buildings.append(pos)
                match bld:
                    case BuildingLauncher(team=t) if t != ct.get_team():
                        for d in DIR8:
                            state.adjacent_to_enemy_launcher.add(pos.add(d))
            else:
                state.buildings[i] = None
