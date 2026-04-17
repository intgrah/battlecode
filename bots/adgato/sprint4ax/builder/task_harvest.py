from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingBridge,
    BuildingConveyor,
    BuildingHarvester,
    BuildingRoad,
    BuildingSplitter,
)
from cambc import Controller, EntityType, Environment
from util import DELTA_TO_DIR, DIR4, DIR_TO_DELTA, INF, can_afford, get_direction_object

from .algorithms.pathfind import conv_pathfind
from .extra import pave
from .helpers import make_move, try_move_with_road

if TYPE_CHECKING:
    from builder import Builder, PosInt


def _find_contest_target(self: Builder, pos: PosInt, my_team) -> PosInt | None:
    """Return the first enemy contestable building (road, conveyor,
    splitter, bridge) adjacent to `pos` that we can destroy by
    standing on it and firing. Roads are included: even though they
    don't siphon Ti directly, an enemy holding roads around our ore
    can upgrade them to conveyors next turn and start siphoning.

    Non-contestable enemies (armoured conveyors, turrets, foundries,
    cores, barriers) are intentionally NOT returned — we can't damage
    or walk on them. The harvester still gets built and we accept the
    fractional Ti leakage.
    """
    for d in DIR4:
        n = pos + d
        if not self.in_bounds(n):
            continue
        b = self.get_building(n)
        if b is None or getattr(b, "team", None) == my_team:
            continue
        if isinstance(
            b, (BuildingRoad, BuildingConveyor, BuildingSplitter, BuildingBridge)
        ):
            return n
    return None


def ore_available(self: Builder, ct: Controller, pos: PosInt) -> bool:
    b = self.get_building(pos)
    if b is not None and not isinstance(b, BuildingRoad):
        return False

    if ct.is_in_vision(self.pos(pos)):
        worker_id = ct.get_tile_builder_bot_id(self.pos(pos))
        if worker_id is not None and worker_id != self.my_id:
            return False

    return True


def pick_ore_target(self: Builder, ct: Controller) -> PosInt:
    current_pos = self.my_pos

    best_target = -1
    min_dist = INF

    for pos in self.nearby_positions:
        terrain = self.get_env(pos)

        if terrain in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE):
            match self.get_building(pos):
                case BuildingHarvester():
                    continue
                case None | BuildingRoad():
                    pass
                case _:
                    continue

            if ore_available(self, ct, pos):
                dist = self.sq_dist(current_pos, pos)
                if dist < min_dist:
                    min_dist = dist
                    best_target = pos

    return best_target


def build_at_ore(self: Builder, ct: Controller, target_pos: PosInt) -> bool:
    my_pos = self.my_pos

    maybe_unpaved = [
        pos
        for d in DIR4
        if self.in_bounds(pos := target_pos + d)
        and ct.is_in_vision(self.pos(pos))
        and self.get_env(pos) != Environment.WALL
    ]
    if pave(self, ct, maybe_unpaved):
        return True

    # Contest step: if an enemy road/conveyor/splitter/bridge is
    # sitting adjacent to this ore, clear it before building the
    # harvester. `pathfind_blocked` can't step onto an impassable
    # (INF cost) goal because the path-extraction formula adds the
    # goal's cost, so for the final step we use a direct ct.move()
    # in the right direction.
    contest_pos = _find_contest_target(self, target_pos, self.my_team)
    if contest_pos is not None:
        if my_pos == contest_pos:
            ti, _ = ct.get_global_resources()
            if ti >= 2 and ct.can_fire(self.pos(my_pos)):
                ct.fire(self.pos(my_pos))
            return True
        if self.my_sq_dist(contest_pos) <= 2:
            d = get_direction_object(my_pos, contest_pos)
            if ct.can_move(d):
                ct.move(d)
                self.my_pos += DIR_TO_DELTA[d]
            return True
        make_move(self, ct, contest_pos)
        return True

    if my_pos == target_pos:
        if not ore_available(self, ct, target_pos):
            self.ore_target = -1
            return False

        if not can_afford(ct, EntityType.HARVESTER):
            return True

        b = self.get_building(my_pos)
        if isinstance(b, BuildingRoad) and ct.can_destroy(self.pos(my_pos)):
            escape_tile = None
            for d in DIR4:
                check_pos = my_pos + d
                if ct.can_move(DELTA_TO_DIR[d]):
                    escape_tile = check_pos
                    break

            if escape_tile:
                ct.destroy(self.pos(my_pos))
            else:
                return True

        preferred_dirs = []
        if self.my_core:
            path = conv_pathfind(self, ct, self.pos(my_pos), self.pos(self.my_core))
            if path and len(path) > 1:
                next_pos = self._idx(path[1])
                d = get_direction_object(my_pos, next_pos)
                if d:
                    preferred_dirs.append(d)

        ortho_preferred = [d for d in preferred_dirs if d in DIR4]
        ortho_others = [d for d in DIR4 if d not in preferred_dirs]
        all_dirs = ortho_preferred + ortho_others

        for d in all_dirs:
            move_pos = my_pos + d
            if self.is_passable(move_pos) and ct.can_move(DELTA_TO_DIR[d]):
                ct.move(DELTA_TO_DIR[d])
                self.my_pos = self.my_pos + d
                if ct.can_build_harvester(self.pos(target_pos)):
                    ct.build_harvester(self.pos(target_pos))
                    self.ore_target = -1
                return True

        return True

    if self.my_sq_dist(target_pos) <= 2:
        if not can_afford(ct, EntityType.HARVESTER):
            if try_move_with_road(self, ct, target_pos):
                return True
            return True

        has_road = isinstance(self.get_building(target_pos), BuildingRoad)

        if has_road:
            if try_move_with_road(self, ct, target_pos):
                return True
        elif (
            ct.can_build_harvester(self.pos(target_pos))
            and self.my_sq_dist(target_pos) <= 1
        ):
            ct.build_harvester(self.pos(target_pos))
            self.ore_target = -1
            return True
        else:
            if self.my_sq_dist(target_pos) > 1:
                for d in DIR4:
                    ortho_pos = target_pos + d
                    if (
                        self.is_passable(ortho_pos) and self.my_sq_dist(ortho_pos) <= 2
                    ) and try_move_with_road(self, ct, ortho_pos):
                        return True

                if try_move_with_road(self, ct, target_pos):
                    return True

                return True

            if ct.can_build_harvester(self.pos(target_pos)):
                ct.build_harvester(self.pos(target_pos))
                self.ore_target = -1
                return True

    return make_move(self, ct, target_pos)
