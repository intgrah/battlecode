from __future__ import annotations

from typing import TYPE_CHECKING

from building import BuildingHarvester, BuildingRoad
from cambc import Controller, Direction, Environment

from .helpers import DIR4, try_move_adj_to

if TYPE_CHECKING:
    from builder import Builder


def fix_enemy_conveyor(self: Builder, ct: Controller) -> bool:
    nearby_positions = ct.get_nearby_tiles(2)
    for pos in nearby_positions:
        if self.leads_to_enemy_building(pos) and ct.can_destroy(pos):
            ct.destroy(pos)
            if ct.can_build_road(pos):
                ct.build_road(pos)
                return True
    return False


def deny_enemy_ore(self: Builder, ct: Controller) -> bool:
    """Opportunistic ore denial: drop a cheap road on a tile that
    would be a harvester-feed candidate for an enemy. Only acts when
    a denial tile is already within action range — no repositioning.
    """
    nearby_positions = ct.get_nearby_tiles(2)
    for pos in nearby_positions:
        if pos not in self.deny_ore_neighbours:
            continue
        if self.get_env(pos) == Environment.WALL:
            continue
        if self.get_building(pos) is not None:
            continue
        if ct.can_build_road(pos):
            ct.build_road(pos)
            return True
    return False


def pave_near_harvesters(self: Builder, ct: Controller) -> bool:
    # Always prefer conveyors adjacent to harvesters. Chain connection
    # is handled by the separate _connect_close / _connect_far tasks
    # via self.dangling_output, so we don't need to call
    # route_to_core here.

    candidates = [
        pos
        for pos in ct.get_nearby_tiles(8)
        if pos in self.adjacent_to_harvester and self.get_env(pos) != Environment.WALL
    ]
    maybe_unpaved = sorted(candidates, key=self.my_pos.distance_squared)

    my_team = self.my_team
    for pos in maybe_unpaved:
        bid = ct.get_tile_building_id(pos)
        if bid is not None and ct.get_team(ct.get_tile_building_id(pos)) != my_team:
            continue

        dir = Direction.CENTRE
        for d in DIR4:
            building = self.get_building(pos.add(d))
            if isinstance(building, BuildingHarvester):
                if building.team == my_team:
                    dir = d
                    break

        is_road = isinstance(self.get_building(pos), BuildingRoad)
        moved = False
        if self.my_pos.distance_squared(pos) > 2 and (bid is None or is_road):
            moved = try_move_adj_to(self, ct, pos)
            if not moved:
                continue

        if is_road and ct.can_destroy(pos):
            ct.destroy(pos)

        if ct.can_build_conveyor(pos, dir):
            ct.build_conveyor(pos, dir)
            return True

        if moved:
            return False

    return False
