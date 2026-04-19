from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingBridge,
    BuildingConveyor,
    BuildingRoad,
    BuildingSplitter,
)
from cambc import Controller, EntityType, Environment, Position, Team
from util.directions import DIR4, get_direction_object

from builder.helpers import can_afford, make_move, ore_available, try_move_with_road

if TYPE_CHECKING:
    from builder import Builder


def _find_contest_target(
    self: Builder,
    pos: Position,
    my_team: Team,
) -> Position | None:
    for d in DIR4:
        n = pos.add(d)
        if not self.in_bounds(n):
            continue
        b = self.get_building(n)
        if b is None or b.team == my_team:
            continue
        if isinstance(
            b,
            (BuildingRoad, BuildingConveyor, BuildingSplitter, BuildingBridge),
        ):
            return n
    return None


def build_at_ore(self: Builder, ct: Controller, target_pos: Position) -> bool:
    # Contest step: if an enemy road/conveyor/splitter/bridge is
    # sitting adjacent to this ore, clear it before building the
    # harvester. `pathfind_blocked` can't step onto an impassable
    # (INF cost) goal because the path-extraction formula adds the
    # goal's cost, so for the final step we use a direct ct.move()
    # in the right direction.
    contest_pos = _find_contest_target(self, target_pos, self.my_team)
    if contest_pos is not None:
        if self.my_pos == contest_pos:
            if self.ti >= 2 and ct.can_fire(self.my_pos):
                ct.fire(self.my_pos)
            return True
        if self.my_pos.distance_squared(contest_pos) <= 2:
            d = self.my_pos.direction_to(contest_pos)
            if ct.can_move(d):
                ct.move(d)
            return True
        make_move(self, ct, contest_pos)
        return True

    neighbors = [target_pos.add(d) for d in DIR4]
    unpaved_neighbors = []
    for n in neighbors:
        if not self.in_bounds(n):
            continue
        if self.get_env(n) == Environment.WALL:
            continue

        b = self.get_building(n)
        if b is None:
            unpaved_neighbors.append(n)
        elif not isinstance(b, BuildingRoad):
            pass

    if self.my_pos == target_pos:
        if not ore_available(self, target_pos):
            self.ore_target = None
            return False

        for n in unpaved_neighbors:
            if n == self.my_pos:
                continue
            if ct.can_build_road(n):
                ct.build_road(n)
                return True

        if not can_afford(self, EntityType.HARVESTER):
            return True

        b = self.get_building(self.my_pos)
        if isinstance(b, BuildingRoad) and ct.can_destroy(self.my_pos):
            escape_tile = None
            for d, check_pos in self.dir_neighbours_4:
                if ct.can_move(d):
                    escape_tile = check_pos
                    break

            if escape_tile:
                ct.destroy(self.my_pos)
            else:
                return True

        preferred_dirs = []
        if self.my_core:
            path = self.conv_search.search(ct, self.my_pos, self.my_core)
            if path and len(path) > 1:
                next_pos = path[1]
                d = get_direction_object(self.my_pos, next_pos)
                if d:
                    preferred_dirs.append(d)

        ortho_preferred = [d for d in preferred_dirs if d in DIR4]
        ortho_others = [d for d in DIR4 if d not in preferred_dirs]
        all_dirs = ortho_preferred + ortho_others

        for d in all_dirs:
            move_pos = self.my_pos.add(d)
            if self.is_passable(move_pos) and ct.can_move(d):
                ct.move(d)
                if ct.can_build_harvester(target_pos):
                    ct.build_harvester(target_pos)
                    self.ore_target = None
                return True

        return True

    if self.my_pos.distance_squared(target_pos) <= 2:
        if unpaved_neighbors:
            for n in unpaved_neighbors:
                if self.my_pos.distance_squared(n) <= 2 and ct.can_build_road(n):
                    ct.build_road(n)
                    return True

            target_has_road = isinstance(self.get_building(target_pos), BuildingRoad)

            if target_has_road:
                if try_move_with_road(self, ct, target_pos):
                    return True
            else:
                target_n = unpaved_neighbors[0]
                path = self.conv_search.search_blocked(ct, self.my_pos, target_n)
                if path and len(path) > 1:
                    try_move_with_road(self, ct, path[1])
                    return True
            return True

        if not can_afford(self, EntityType.HARVESTER):
            if try_move_with_road(self, ct, target_pos):
                return True
            return True

        has_road = isinstance(self.get_building(target_pos), BuildingRoad)

        if has_road:
            if try_move_with_road(self, ct, target_pos):
                return True
        elif (
            ct.can_build_harvester(target_pos)
            and self.my_pos.distance_squared(target_pos) <= 1
        ):
            ct.build_harvester(target_pos)
            self.ore_target = None
            return True
        else:
            if self.my_pos.distance_squared(target_pos) > 1:
                for d in DIR4:
                    ortho_pos = target_pos.add(d)
                    if (
                        self.is_passable(ortho_pos)
                        and self.my_pos.distance_squared(ortho_pos) <= 2
                    ) and try_move_with_road(self, ct, ortho_pos):
                        return True

                if try_move_with_road(self, ct, target_pos):
                    return True

                return True

            if ct.can_build_harvester(target_pos):
                ct.build_harvester(target_pos)
                self.ore_target = None
                return True

    return make_move(self, ct, target_pos)
