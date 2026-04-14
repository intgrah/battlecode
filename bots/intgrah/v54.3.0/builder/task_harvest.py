from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingBridge,
    BuildingConveyor,
    BuildingRoad,
    BuildingSplitter,
)
from cambc import Controller, EntityType, Environment, Position, Team
from util import DIR4, can_afford, get_direction_object

from builder.algorithms.econ_astar import conv_search
from builder.helpers import make_move, ore_available, try_move_with_road

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
    my_pos = ct.get_position()

    # Contest step: if an enemy road/conveyor/splitter/bridge is
    # sitting adjacent to this ore, clear it before building the
    # harvester. `pathfind_blocked` can't step onto an impassable
    # (INF cost) goal because the path-extraction formula adds the
    # goal's cost, so for the final step we use a direct ct.move()
    # in the right direction.
    contest_pos = _find_contest_target(self, target_pos, ct.get_team())
    if contest_pos is not None:
        if my_pos == contest_pos:
            ti, _ = ct.get_global_resources()
            if ti >= 2 and ct.can_fire(my_pos):
                ct.fire(my_pos)
            return True
        if my_pos.distance_squared(contest_pos) <= 2:
            d = my_pos.direction_to(contest_pos)
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

    if my_pos == target_pos:
        if not ore_available(self, ct, target_pos):
            self.ore_target = None
            return False

        for n in unpaved_neighbors:
            if n == my_pos:
                continue
            if ct.can_build_road(n):
                ct.build_road(n)
                return True

        if not can_afford(ct, EntityType.HARVESTER):
            return True

        b = self.get_building(my_pos)
        if isinstance(b, BuildingRoad) and ct.can_destroy(my_pos):
            escape_tile = None
            for d in DIR4:
                check_pos = my_pos.add(d)
                if ct.can_move(d):
                    escape_tile = check_pos
                    break

            if escape_tile:
                ct.destroy(my_pos)
            else:
                return True

        preferred_dirs = []
        if self.my_core:
            path = conv_search.search(self, ct, my_pos, self.my_core)
            if path and len(path) > 1:
                next_pos = path[1]
                d = get_direction_object(my_pos, next_pos)
                if d:
                    preferred_dirs.append(d)

        ortho_preferred = [d for d in preferred_dirs if d in DIR4]
        ortho_others = [d for d in DIR4 if d not in preferred_dirs]
        all_dirs = ortho_preferred + ortho_others

        for d in all_dirs:
            move_pos = my_pos.add(d)
            if self.is_passable(move_pos) and ct.can_move(d):
                ct.move(d)
                if ct.can_build_harvester(target_pos):
                    ct.build_harvester(target_pos)
                    self.ore_target = None
                return True

        return True

    if my_pos.distance_squared(target_pos) <= 2:
        if unpaved_neighbors:
            for n in unpaved_neighbors:
                if my_pos.distance_squared(n) <= 2 and ct.can_build_road(n):
                    ct.build_road(n)
                    return True

            target_has_road = isinstance(self.get_building(target_pos), BuildingRoad)

            if target_has_road:
                if try_move_with_road(self, ct, target_pos):
                    return True
            else:
                target_n = unpaved_neighbors[0]
                path = conv_search.search_blocked(self, ct, my_pos, target_n)
                if path and len(path) > 1:
                    try_move_with_road(self, ct, path[1])
                    return True
            return True

        if not can_afford(ct, EntityType.HARVESTER):
            if try_move_with_road(self, ct, target_pos):
                return True
            return True

        has_road = isinstance(self.get_building(target_pos), BuildingRoad)

        if has_road:
            if try_move_with_road(self, ct, target_pos):
                return True
        elif (
            ct.can_build_harvester(target_pos)
            and my_pos.distance_squared(target_pos) <= 1
        ):
            ct.build_harvester(target_pos)
            self.ore_target = None
            return True
        else:
            if my_pos.distance_squared(target_pos) > 1:
                for d in DIR4:
                    ortho_pos = target_pos.add(d)
                    if (
                        self.is_passable(ortho_pos)
                        and my_pos.distance_squared(ortho_pos) <= 2
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
