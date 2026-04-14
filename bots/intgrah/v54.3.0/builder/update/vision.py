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

if TYPE_CHECKING:
    from builder import Builder


def update_vision(self: Builder, ct: Controller) -> None:
    w = self.w
    pad = self.pad
    pw = self.pw
    my_team = ct.get_team()
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
                        case _:
                            code = 3
                    self.flow_history[i] = (self.flow_history[i] & ~(3 << shift)) | (
                        code << shift
                    )

            match bld:
                case BuildingConveyor(direction=d):
                    target_pos = pos.add(d)
                    if 0 <= target_pos.x < self.w and 0 <= target_pos.y < self.h:
                        ti = target_pos.y * w + target_pos.x
                        self.conveyors_to_here[ti].append(pos)
                case BuildingBridge(target=t):
                    if 0 <= t.x < self.w and 0 <= t.y < self.h:
                        ti = t.y * w + t.x
                        self.conveyors_to_here[ti].append(pos)
                case BuildingSplitter(direction=d):
                    for sd in [
                        d,
                        d.rotate_right().rotate_right(),
                        d.rotate_left().rotate_left(),
                    ]:
                        target_pos = pos.add(sd)
                        if 0 <= target_pos.x < self.w and 0 <= target_pos.y < self.h:
                            ti = target_pos.y * w + target_pos.x
                            self.splitters_to_here[ti].append(pos)

            self.nearby_buildings.append(pos)
            if self.hp[i] < self.max_hp[i] and bld is not None and bld.team == my_team:
                self.healable_buildings.append(pos)
            match bld:
                case BuildingLauncher(team=t) if t != my_team:
                    for d in DIR8:
                        n = pos.add(d)
                        if 0 <= n.x < self.w and 0 <= n.y < self.h:
                            self.adjacent_to_enemy_launcher.add(n)
                case BuildingGunner(team=t, direction=d) if t != my_team:
                    ray = pos
                    for _ in range(4):
                        ray = ray.add(d)
                        if pos.distance_squared(ray) > 13:
                            break
                        if 0 <= ray.x < self.w and 0 <= ray.y < self.h:
                            self.enemy_turret_ray_tiles.add(ray)
                case BuildingSentinel(team=t, direction=d) if t != my_team:
                    ray = pos
                    for _ in range(6):
                        ray = ray.add(d)
                        if pos.distance_squared(ray) > 32:
                            break
                        if 0 <= ray.x < self.w and 0 <= ray.y < self.h:
                            self.enemy_turret_ray_tiles.add(ray)
                        for hd in DIR8:
                            h = ray.add(hd)
                            if 0 <= h.x < self.w and 0 <= h.y < self.h:
                                self.enemy_turret_ray_tiles.add(h)
                case BuildingGunner(team=t, direction=d) if t == my_team:
                    ray = pos
                    for _ in range(4):
                        ray = ray.add(d)
                        if pos.distance_squared(ray) > 13:
                            break
                        if not (0 <= ray.x < self.w and 0 <= ray.y < self.h):
                            break
                        if self.get_env(ray) == Environment.WALL:
                            break
                        self.friendly_turret_ray_tiles.add(ray)
                        if self.get_building(ray) is not None:
                            break
                case BuildingSentinel(team=t, direction=d) if t == my_team:
                    ray = pos
                    for _ in range(6):
                        ray = ray.add(d)
                        if pos.distance_squared(ray) > 32:
                            break
                        if not (0 <= ray.x < self.w and 0 <= ray.y < self.h):
                            break
                        if self.get_env(ray) == Environment.WALL:
                            break
                        self.friendly_turret_ray_tiles.add(ray)
                        for hd in DIR8:
                            h = ray.add(hd)
                            if 0 <= h.x < self.w and 0 <= h.y < self.h:
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
        self.cost_grid[pi] = cost
        self.conveyor_cost_grid[pi] = conveyor_cost
        self.update_pnb(i)
