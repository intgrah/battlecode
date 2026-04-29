from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingArmouredConveyor,
    BuildingBarrier,
    BuildingBridge,
    BuildingConveyor,
    BuildingMarker,
    BuildingRoad,
    BuildingSplitter,
)
from cambc import Controller, EntityType, Environment, Position, Team
from util.debug import debug as log
from util.directions import DIR4, get_direction_object

from builder.helpers import (
    can_afford,
    harvester_feed_cardinal,
    harvester_io_cardinals,
    make_move,
    ore_available,
    try_move_with_road,
    try_place,
)

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
    log(
        f"build_at_ore: starting work to build a harvester on ore tile "
        f"{target_pos} (builder is currently at {self.my_pos})",
    )
    # Contest step: if an enemy road/conveyor/splitter/bridge is
    # sitting adjacent to this ore, clear it before building the
    # harvester. `pathfind_blocked` can't step onto an impassable
    # (INF cost) goal because the path-extraction formula adds the
    # goal's cost, so for the final step we use a direct ct.move()
    # in the right direction.
    contest_pos = _find_contest_target(self, target_pos, self.my_team)
    if contest_pos is not None:
        log(
            f"build_at_ore: CONTEST phase — enemy road/conveyor/splitter/bridge "
            f"at {contest_pos} is adjacent to ore {target_pos}; must clear it "
            "before placing harvester (otherwise the harvester's cardinal "
            "neighbour would dump mined ore into an enemy conveyor)",
        )
        if self.my_pos == contest_pos:
            if self.ti >= 2 and ct.can_fire(self.my_pos):
                log(
                    f"build_at_ore: standing on contest tile {self.my_pos}, "
                    "firing to damage the enemy building underneath",
                )
                ct.fire(self.my_pos)
            return True
        if self.my_pos.distance_squared(contest_pos) <= 2:
            d = self.my_pos.direction_to(contest_pos)
            if ct.can_move(d):
                log(
                    f"build_at_ore: walking onto contest tile {contest_pos} "
                    f"(direction {d}) to stand on the enemy building and destroy it",
                )
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
        # Treat empties, friendly roads, and markers as available for
        # barrier placement — all cheaply destroyable.
        if b is None or isinstance(b, BuildingRoad | BuildingMarker):
            unpaved_neighbors.append(n)
        elif not isinstance(b, BuildingRoad):
            pass

    if self.my_pos == target_pos:
        log(
            f"build_at_ore: builder is standing on the ore tile {target_pos}; "
            "the harvester will be placed here but the builder must step off "
            "first (can_build_harvester requires empty tile)",
        )
        if not ore_available(self, target_pos):
            log(
                f"build_at_ore: ore tile {target_pos} is no longer available "
                "(another unit is on it or a building was placed); clearing "
                "ore_target so a new one can be picked next turn",
            )
            self.ore_target = None
            return False

        # Guard the cardinals that aren't reserved as flow I/O for this
        # (or an adjacent) harvester. Inward-facing conveyors do double
        # duty: they're more durable than walking on roads, deny the
        # tile to enemy parasites, and the dangling-end check ignores
        # them (a conveyor pointing INTO the harvester isn't a flow
        # consumer, so it doesn't show up as a stray dangling end).
        #
        # Skip when `harvester_feed_cardinal` returned None: every
        # cardinal candidate is a dead-end pocket and ringing the
        # harvester would seal it off completely.
        feed = harvester_feed_cardinal(self, target_pos)
        if feed is None:
            log(
                f"build_at_ore: no viable feed cardinal for ore "
                f"{target_pos}; skipping inward-conveyor ring",
            )
        else:
            io_reserved = harvester_io_cardinals(self, target_pos)
            for n in unpaved_neighbors:
                if n == self.my_pos or n in io_reserved:
                    continue
                inward = n.direction_to(target_pos)
                # Tear down a friendly road on this tile so we can
                # replace it with a conveyor.
                if (
                    isinstance(self.get_building(n), BuildingRoad)
                    and ct.can_destroy(n)
                    and can_afford(self, EntityType.CONVEYOR)
                ):
                    ct.destroy(n)
                if (
                    can_afford(self, EntityType.CONVEYOR)
                    and ct.can_build_conveyor(n, inward)
                ):
                    log(
                        f"build_at_ore: inward CONVEYOR at neighbour {n} "
                        f"facing {inward} into ore {target_pos}",
                    )
                    ct.build_conveyor(n, inward)
                    return True

        # All non-IO cardinals barriered (or unaffordable). Pave the
        # chosen feed cardinal with a road so an enemy can't squat-
        # build a free conveyor there and steal the harvester's output
        # the moment it spawns.
        feed = harvester_feed_cardinal(self, target_pos)
        if feed is not None and ct.can_build_road(feed):
            log(
                f"build_at_ore: ROAD on feed cardinal {feed} of ore "
                f"{target_pos} (deny enemy squat-feeder)",
            )
            ct.build_road(feed)
            return True

        if not can_afford(self, EntityType.HARVESTER):
            log(
                f"build_at_ore: cannot afford HARVESTER yet (ti={self.ti}), "
                f"builder is waiting on ore tile {target_pos} for income",
            )
            return True

        b = self.get_building(self.my_pos)
        if isinstance(b, BuildingRoad) and ct.can_destroy(self.my_pos):
            escape_tile = None
            for d, check_pos in self.dir_neighbours_4:
                if ct.can_move(d):
                    escape_tile = check_pos
                    break

            if escape_tile:
                log(
                    f"build_at_ore: destroying own ROAD at {self.my_pos} to "
                    "clear the ore tile (will step off to "
                    f"{escape_tile} in the next action this turn)",
                )
                ct.destroy(self.my_pos)
            else:
                log(
                    f"build_at_ore: cannot escape from ore tile {self.my_pos} "
                    "(no moveable direction); waiting another turn",
                )
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
                log(
                    f"build_at_ore: stepping off ore {target_pos} in direction "
                    f"{d} (to {move_pos}) and then placing HARVESTER on the "
                    "vacated ore tile in the same turn",
                )
                ct.move(d)
                if ct.can_build_harvester(target_pos):
                    log(
                        f"build_at_ore: placed HARVESTER at {target_pos} "
                        "(ore_target cleared; will mine 1 stack every 4 turns)",
                    )
                    ct.build_harvester(target_pos)
                    self.ore_target = None
                return True

        return True

    if self.my_pos.distance_squared(target_pos) <= 2:
        # If the ore tile itself has a friendly barrier on it (placed
        # earlier as the protective ring of an ADJACENT harvester),
        # tear it down so we can walk onto the ore. The neighbouring
        # harvester loses one face of its ring in return — temporarily
        # acceptable, since we'll fill the gap with this new harvester
        # plus its own ring.
        existing = self.get_building(target_pos)
        if (
            isinstance(
                existing,
                BuildingBarrier | BuildingConveyor | BuildingArmouredConveyor,
            )
            and ct.can_destroy(target_pos)
        ):
            log(
                f"build_at_ore: destroying friendly guard on ore "
                f"{target_pos} so we can claim it for a new harvester",
            )
            ct.destroy(target_pos)
            # Fall through — destroy is its own action, but the builder
            # still has its move action available this turn so it can
            # walk onto the now-empty ore tile in the same turn.

        if unpaved_neighbors:
            # Walk onto the ore first to signal claim. Barriers are
            # placed from there next turn — standing on the ore puts
            # every cardinal in action range, so we lay all barriers
            # from one position rather than orbit the tile.
            log(
                f"build_at_ore: walking onto ore {target_pos} to claim it; "
                "barriers will be placed from there next turn",
            )
            if try_move_with_road(self, ct, target_pos):
                return True
            return True

        if not can_afford(self, EntityType.HARVESTER):
            log(
                f"build_at_ore: close to ore {target_pos} but cannot afford "
                f"HARVESTER (ti={self.ti}); walking onto ore to wait",
            )
            if try_move_with_road(self, ct, target_pos):
                return True
            return True

        has_road = isinstance(self.get_building(target_pos), BuildingRoad)

        if has_road:
            log(
                f"build_at_ore: walking onto ore {target_pos} (road exists, so "
                "we can step onto it for cheap)",
            )
            if try_move_with_road(self, ct, target_pos):
                return True
        elif (
            ct.can_build_harvester(target_pos)
            and self.my_pos.distance_squared(target_pos) <= 1
        ):
            log(
                f"build_at_ore: placing HARVESTER at {target_pos} from cardinal "
                f"neighbour {self.my_pos} (no need to step onto ore)",
            )
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
                        log(
                            f"build_at_ore: repositioning to cardinal neighbour "
                            f"{ortho_pos} of ore {target_pos} (we were diagonal, "
                            "need cardinal to place harvester from adjacent)",
                        )
                        return True

                if try_move_with_road(self, ct, target_pos):
                    return True

                return True

            if ct.can_build_harvester(target_pos):
                log(
                    f"build_at_ore: placing HARVESTER at {target_pos} from "
                    f"cardinal neighbour {self.my_pos}",
                )
                ct.build_harvester(target_pos)
                self.ore_target = None
                return True

    log(
        f"build_at_ore: builder at {self.my_pos} is far from ore {target_pos} "
        f"(dist_sq={self.my_pos.distance_squared(target_pos)}); walking toward it",
    )
    return make_move(self, ct, target_pos)
