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
from cambc import Controller, EntityType, Environment, GameConstants, ResourceType
from util import DIR8, INF, ROAD_COST

if TYPE_CHECKING:
    from builder import Builder


def update_vision(self: Builder, ct: Controller) -> None:
    w = self.w
    pad = self.pad
    pw = self.pad_w
    for pos in self.nearby_positions:
        i = pos.y * w + pos.x
        pi = (pos.y + pad) * pw + (pos.x + pad)
        self.env[i] = ct.get_tile_env(pos)
        building_id = ct.get_tile_building_id(pos)
        if (
            building_id is not None
            and ct.get_entity_type(building_id) != EntityType.MARKER
        ):
            etype = ct.get_entity_type(building_id)
            bld = make_building(ct, building_id, etype)
            self.buildings[i] = bld
            self.hp[i] = ct.get_hp(building_id)
            self.max_hp[i] = ct.get_max_hp(building_id)

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
                        case ResourceType.REFINED_AXIONITE:
                            code = 3
                    self.flow_history[i] = (self.flow_history[i] & ~(0b11 << shift)) | (
                        code << shift
                    )

            match bld:
                case BuildingConveyor(direction=d):
                    t = pos.add(d)
                    if self.in_bounds(t):
                        self.conveyors_to_here[self.idx(t)].append(pos)
                case BuildingBridge(target=t):
                    if self.in_bounds(t):
                        self.conveyors_to_here[self.idx(t)].append(pos)
                case BuildingSplitter(direction=d):
                    for sd in [
                        d,
                        d.rotate_right().rotate_right(),
                        d.rotate_left().rotate_left(),
                    ]:
                        t = pos.add(sd)
                        if self.in_bounds(t):
                            self.splitters_to_here[self.idx(t)].append(pos)

            self.nearby_buildings.append(pos)
            if (
                self.hp[i] < self.max_hp[i]
                and bld is not None
                and bld.team == self.my_team
            ):
                self.healable_buildings.append(pos)
            match bld:
                case BuildingLauncher(team=t) if t != self.my_team:
                    for d in DIR8:
                        n = pos.add(d)
                        if self.in_bounds(n):
                            self.adjacent_to_enemy_launcher.add(n)
                case BuildingGunner(team=t, direction=d) if t != self.my_team:
                    ray = pos
                    for _ in range(4):
                        ray = ray.add(d)
                        if (
                            pos.distance_squared(ray)
                            > GameConstants.GUNNER_VISION_RADIUS_SQ
                        ):
                            break
                        if self.in_bounds(ray):
                            self.enemy_turret_ray_tiles.add(ray)
                case BuildingSentinel(team=t, direction=d) if t != self.my_team:
                    ray = pos
                    for _ in range(6):
                        ray = ray.add(d)
                        if (
                            pos.distance_squared(ray)
                            > GameConstants.SENTINEL_VISION_RADIUS_SQ
                        ):
                            break
                        if self.in_bounds(ray):
                            self.enemy_turret_ray_tiles.add(ray)
                        for hd in DIR8:
                            h = ray.add(hd)
                            if self.in_bounds(h):
                                self.enemy_turret_ray_tiles.add(h)
                case BuildingGunner(team=t, direction=d) if t == self.my_team:
                    ray = pos
                    for _ in range(4):
                        ray = ray.add(d)
                        if (
                            pos.distance_squared(ray)
                            > GameConstants.GUNNER_VISION_RADIUS_SQ
                        ):
                            break
                        if not self.in_bounds(ray):
                            break
                        if self.get_env(ray) == Environment.WALL:
                            break
                        self.friendly_turret_ray_tiles.add(ray)
                        if self.get_building(ray) is not None:
                            break
                case BuildingSentinel(team=t, direction=d) if t == self.my_team:
                    ray = pos
                    for _ in range(6):
                        ray = ray.add(d)
                        if pos.distance_squared(ray) > 32:
                            break
                        if not self.in_bounds(ray):
                            break
                        if self.get_env(ray) == Environment.WALL:
                            break
                        self.friendly_turret_ray_tiles.add(ray)
                        for hd in DIR8:
                            h = ray.add(hd)
                            if self.in_bounds(h):
                                self.friendly_turret_ray_tiles.add(h)
                        if self.get_building(ray) is not None:
                            break
        else:
            self.buildings[i] = None

        terrain = self.env[i]
        bld = self.buildings[i]
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
                case BuildingCore(team=t) if t == self.my_team:
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
        self.cost_grid[pi] = cost
        self.conveyor_cost_grid[pi] = conveyor_cost
        self.update_pnb(i)
