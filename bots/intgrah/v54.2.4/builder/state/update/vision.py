from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingCore,
    BuildingGunner,
    BuildingLauncher,
    BuildingRoad,
    BuildingSentinel,
    BuildingSplitter,
    make_building,
)
from cambc import Controller, EntityType, Environment, ResourceType
from util import DIR8, INF, ROAD_COST

from builder.state import update_pnb

if TYPE_CHECKING:
    from builder.state import State


def update_vision(state: State, ct: Controller) -> None:
    w = state.w
    pad = state.pad
    pw = state.pw
    my_team = ct.get_team()
    for pos in state.nearby_positions:
        i = pos.y * w + pos.x
        pi = (pos.y + pad) * pw + (pos.x + pad)
        state.env[i] = ct.get_tile_env(pos)
        building_id = ct.get_tile_building_id(pos)
        if (
            building_id is not None
            and ct.get_entity_type(building_id) != EntityType.MARKER
        ):
            etype = ct.get_entity_type(building_id)
            bld = make_building(ct, building_id, etype)
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
                    state.flow_history[i] = (state.flow_history[i] & ~(3 << shift)) | (
                        code << shift
                    )

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
                        if 0 <= target_pos.x < state.w and 0 <= target_pos.y < state.h:
                            ti = target_pos.y * w + target_pos.x
                            state.splitters_to_here[ti].append(pos)

            state.nearby_buildings.append(pos)
            if (
                state.hp[i] < state.max_hp[i]
                and bld is not None
                and bld.team == my_team
            ):
                state.healable_buildings.append(pos)
            match bld:
                case BuildingLauncher(team=t) if t != my_team:
                    for d in DIR8:
                        n = pos.add(d)
                        if 0 <= n.x < state.w and 0 <= n.y < state.h:
                            state.adjacent_to_enemy_launcher.add(n)
                case BuildingGunner(team=t, direction=d) if t != my_team:
                    ray = pos
                    for _ in range(4):
                        ray = ray.add(d)
                        if pos.distance_squared(ray) > 13:
                            break
                        if 0 <= ray.x < state.w and 0 <= ray.y < state.h:
                            state.enemy_turret_ray_tiles.add(ray)
                case BuildingSentinel(team=t, direction=d) if t != my_team:
                    ray = pos
                    for _ in range(6):
                        ray = ray.add(d)
                        if pos.distance_squared(ray) > 32:
                            break
                        if 0 <= ray.x < state.w and 0 <= ray.y < state.h:
                            state.enemy_turret_ray_tiles.add(ray)
                        for hd in DIR8:
                            h = ray.add(hd)
                            if 0 <= h.x < state.w and 0 <= h.y < state.h:
                                state.enemy_turret_ray_tiles.add(h)
                case BuildingGunner(team=t, direction=d) if t == my_team:
                    ray = pos
                    for _ in range(4):
                        ray = ray.add(d)
                        if pos.distance_squared(ray) > 13:
                            break
                        if not (0 <= ray.x < state.w and 0 <= ray.y < state.h):
                            break
                        if state.get_env(ray) == Environment.WALL:
                            break
                        state.friendly_turret_ray_tiles.add(ray)
                        if state.get_building(ray) is not None:
                            break
                case BuildingSentinel(team=t, direction=d) if t == my_team:
                    ray = pos
                    for _ in range(6):
                        ray = ray.add(d)
                        if pos.distance_squared(ray) > 32:
                            break
                        if not (0 <= ray.x < state.w and 0 <= ray.y < state.h):
                            break
                        if state.get_env(ray) == Environment.WALL:
                            break
                        state.friendly_turret_ray_tiles.add(ray)
                        for hd in DIR8:
                            h = ray.add(hd)
                            if 0 <= h.x < state.w and 0 <= h.y < state.h:
                                state.friendly_turret_ray_tiles.add(h)
                        if state.get_building(ray) is not None:
                            break
        else:
            state.buildings[i] = None

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
                    cost = 1
                    conveyor_cost = 1
                case BuildingCore(team=t) if t == my_team:
                    cost = 1
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
            conveyor_cost = 1 if terrain == Environment.EMPTY else 10
        else:
            cost = 1
            conveyor_cost = 1
        state.cost_grid[pi] = cost
        state.conveyor_cost_grid[pi] = conveyor_cost
        update_pnb(state.w, state.h, state.cost_grid, pw, pad, state.pnb, i)
