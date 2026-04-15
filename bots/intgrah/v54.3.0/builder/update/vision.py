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
from cambc import Controller, EntityType, Environment, GameConstants
from util import DIR8, INF, ROAD_COST

if TYPE_CHECKING:
    from cambc import Position

    from builder import Builder


def _remove_topology(self: Builder, pos: Position, i: int) -> None:
    old_bld = self.buildings[i]
    match old_bld:
        case BuildingConveyor(direction=d):
            t = pos.add(d)
            if self.in_bounds(t):
                ti = self.idx(t)
                lst = self.conveyors_to_here[ti]
                if pos in lst:
                    lst.remove(pos)
        case BuildingBridge(target=t):
            if self.in_bounds(t):
                ti = self.idx(t)
                lst = self.conveyors_to_here[ti]
                if pos in lst:
                    lst.remove(pos)
        case BuildingSplitter(direction=d):
            for sd in [
                d,
                d.rotate_right().rotate_right(),
                d.rotate_left().rotate_left(),
            ]:
                t = pos.add(sd)
                if self.in_bounds(t):
                    ti = self.idx(t)
                    lst = self.splitters_to_here[ti]
                    if pos in lst:
                        lst.remove(pos)


def _add_topology(self: Builder, pos: Position, bld: object) -> None:
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


def _update_cost(
    self: Builder,
    pi: int,
    terrain: Environment | None,
    bld: object,
) -> None:
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


def _update_turret_rays(
    self: Builder,
    ct: Controller,
    pos: Position,
    bld: object,
) -> None:
    match bld:
        case BuildingLauncher(team=t) if t != self.my_team:
            for d in DIR8:
                n = pos.add(d)
                if self.in_bounds(n):
                    self.adjacent_to_enemy_launcher.add(n)
        case BuildingGunner(team=t, direction=d) if t != self.my_team:
            ray = pos
            for _ in range(3):
                ray = ray.add(d)
                if pos.distance_squared(ray) > GameConstants.GUNNER_VISION_RADIUS_SQ:
                    break
                if self.in_bounds(ray):
                    self.enemy_turret_ray_tiles.add(ray)
        case BuildingSentinel(team=t, direction=d) if t != self.my_team:
            for tile in ct.get_attackable_tiles_from(pos, d, EntityType.SENTINEL):
                self.enemy_turret_ray_tiles.add(tile)
        case BuildingGunner(team=t, direction=d) if t == self.my_team:
            ray = pos
            for _ in range(3):
                ray = ray.add(d)
                if pos.distance_squared(ray) > GameConstants.GUNNER_VISION_RADIUS_SQ:
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


def update_vision(self: Builder, ct: Controller) -> None:
    w = self.w
    pad = self.pad
    pw = self.pad_w
    for pos in self.nearby_tiles:
        i = pos.y * w + pos.x
        pi = (pos.y + pad) * pw + (pos.x + pad)

        env = ct.get_tile_env(pos)
        building_id = ct.get_tile_building_id(pos)
        if (
            building_id is not None
            and ct.get_entity_type(building_id) == EntityType.MARKER
        ):
            building_id = None

        env_changed = self.env[i] != env
        old_bid = self.building_ids[i]
        bld_changed = old_bid != building_id

        if env_changed:
            self.env[i] = env

        if bld_changed or env_changed:
            self.building_ids[i] = building_id
            if bld_changed:
                _remove_topology(self, pos, i)
            if building_id is not None:
                etype = ct.get_entity_type(building_id)
                bld = make_building(ct, building_id, etype)
                self.buildings[i] = bld
                self.hp[i] = ct.get_hp(building_id)
                self.max_hp[i] = ct.get_max_hp(building_id)
                _add_topology(self, pos, bld)
            else:
                self.buildings[i] = None
                self.hp[i] = 0
                self.max_hp[i] = 0

            _update_cost(self, pi, env, self.buildings[i])
            self.update_pnb(i)
            bld = self.buildings[i]
            if bld is not None:
                _update_turret_rays(self, ct, pos, bld)
        else:
            bld = self.buildings[i]
            if building_id is not None:
                self.hp[i] = ct.get_hp(building_id)
                self.max_hp[i] = ct.get_max_hp(building_id)

        if building_id is not None:
            bld = self.buildings[i]
            self.nearby_buildings.append(pos)
            if (
                self.hp[i] < self.max_hp[i]
                and bld is not None
                and bld.team == self.my_team
            ):
                self.healable_buildings.append(pos)

            match bld:
                case BuildingConveyor() | BuildingBridge() | BuildingSplitter():
                    self.flow_history[i].append(ct.get_stored_resource(building_id))
