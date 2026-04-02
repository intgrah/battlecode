"""v3 bot - economy with proper conveyor chains.

Strategy:
  - Core: spawn builders assigned to different sectors
  - Builders: explore outward, build harvesters on cardinally-adjacent ore,
    lay conveyor chains back to core, then continue exploring NEW territory
  - Visited-tile tracking prevents oscillation and wall-hugging
  - Robust stuck handling during conveyor laying
"""

from enum import Enum

from cambc import Controller, Direction, EntityType, Environment, Position


class Phase(Enum):
    EXPLORE = "explore"
    LAY_CONVEYORS = "lay_conveyors"


CARDINAL = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]
ALL_DIRS = [d for d in Direction if d != Direction.CENTRE]

SECTOR_DIRS = [
    Direction.NORTH,
    Direction.EAST,
    Direction.SOUTH,
    Direction.WEST,
    Direction.NORTHEAST,
    Direction.SOUTHEAST,
    Direction.SOUTHWEST,
    Direction.NORTHWEST,
]


# ── Helpers ───────────────────────────────────────────────────────────


def in_bounds(ct: Controller, p: Position) -> bool:
    return 0 <= p.x < ct.get_map_width() and 0 <= p.y < ct.get_map_height()


def snap_cardinal(d: Direction) -> Direction:
    """Snap any direction to the nearest cardinal."""
    return {
        Direction.NORTH: Direction.NORTH,
        Direction.SOUTH: Direction.SOUTH,
        Direction.EAST: Direction.EAST,
        Direction.WEST: Direction.WEST,
        Direction.NORTHEAST: Direction.EAST,
        Direction.NORTHWEST: Direction.NORTH,
        Direction.SOUTHEAST: Direction.SOUTH,
        Direction.SOUTHWEST: Direction.WEST,
        Direction.CENTRE: Direction.NORTH,
    }[d]


def cardinal_toward(src: Position, dst: Position) -> Direction:
    """Best cardinal direction from src toward dst."""
    dx = dst.x - src.x
    dy = dst.y - src.y
    if abs(dx) >= abs(dy):
        return Direction.EAST if dx > 0 else Direction.WEST
    return Direction.SOUTH if dy > 0 else Direction.NORTH


def cardinal_priority(preferred: Direction) -> list[Direction]:
    """All 4 cardinals ordered by similarity to preferred (opposite last)."""
    opp = preferred.opposite()
    perps = [d for d in CARDINAL if d not in (preferred, opp)]
    return [preferred, *perps, opp]


def try_move(
    ct: Controller,
    pos: Position,
    direction: Direction,
    build_road: bool = True,
) -> bool:
    """Try to move in direction, building a road if needed. Returns True if moved."""
    target = pos.add(direction)
    if not in_bounds(ct, target):
        return False
    if build_road and ct.get_action_cooldown() == 0 and ct.can_build_road(target):
        ct.build_road(target)
    if ct.can_move(direction):
        ct.move(direction)
        return True
    return False


def try_move_toward(ct: Controller, pos: Position, target: Position) -> bool:
    """Move toward target using cardinal directions with fallback."""
    if ct.get_move_cooldown() > 0:
        return False
    for d in cardinal_priority(cardinal_toward(pos, target)):
        if try_move(ct, pos, d):
            return True
    return False


def find_nearest_ore(ct: Controller, pos: Position) -> Position | None:
    """Find nearest visible unharvested ore tile."""
    best, best_dist = None, 999999
    for tile in ct.get_nearby_tiles():
        env = ct.get_tile_env(tile)
        if (
            env in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE)
            and ct.get_tile_building_id(tile) is None
        ):
            d = pos.distance_squared(tile)
            if d < best_dist:
                best_dist = d
                best = tile
    return best


def find_core(ct: Controller) -> Position | None:
    my_team = ct.get_team()
    for eid in ct.get_nearby_buildings():
        if ct.get_entity_type(eid) == EntityType.CORE and ct.get_team(eid) == my_team:
            return ct.get_position(eid)
    return None


def is_on_core(pos: Position, core_pos: Position) -> bool:
    return abs(pos.x - core_pos.x) <= 1 and abs(pos.y - core_pos.y) <= 1


CONVEYOR_TYPES = {
    EntityType.CONVEYOR,
    EntityType.SPLITTER,
    EntityType.ARMOURED_CONVEYOR,
}


def tile_has_friendly_conveyor(ct: Controller, pos: Position) -> bool:
    """Check if pos has a friendly conveyor/splitter/armoured_conveyor that we can feed into."""
    bid = ct.get_tile_building_id(pos)
    if bid is None:
        return False
    if ct.get_team(bid) != ct.get_team():
        return False
    return ct.get_entity_type(bid) in CONVEYOR_TYPES


def can_feed_into(ct: Controller, from_pos: Position, conv_pos: Position) -> bool:
    """Check if a conveyor at conv_pos can accept input from from_pos.

    A conveyor accepts from its 3 non-output cardinal sides.
    """
    bid = ct.get_tile_building_id(conv_pos)
    if bid is None:
        return False
    try:
        facing = ct.get_direction(bid)
    except Exception:
        return False
    # The conveyor outputs in `facing` direction. It rejects input from that same side.
    # from_pos is feeding into conv_pos. The direction from conv_pos to from_pos must NOT
    # be the conveyor's facing direction.
    feed_dir = cardinal_toward(conv_pos, from_pos)
    return feed_dir != facing


def clean_path(path: list[Position]) -> list[Position]:
    """Remove oscillations and loops from a path.

    Keeps only the LAST visit to each position, producing a loop-free path.
    """
    last_seen: dict[Position, int] = {}
    for i, p in enumerate(path):
        last_seen[p] = i
    result = []
    i = 0
    while i < len(path):
        p = path[i]
        result.append(p)
        i = last_seen[p] + 1
    return result


# ── Player ────────────────────────────────────────────────────────────


class Player:
    def __init__(self) -> None:
        self.spawned = 0
        self.core_pos: Position | None = None
        self.phase: Phase = Phase.EXPLORE
        self.sector: Direction | None = None
        self.path: list[Position] = []
        self.return_path: list[Position] = []
        self.return_idx = 0
        self.stuck_turns = 0
        self.harvester_dir: Direction = Direction.NORTH
        # Persistent across explore cycles — prevents revisiting
        self.visited: set[Position] = set()
        self.explore_stale = 0  # turns without visiting a new tile

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            self._run_core(ct)
        elif etype == EntityType.BUILDER_BOT:
            self._run_builder(ct)

    # ── Core ──────────────────────────────────────────────────────────

    def _run_core(self, ct: Controller) -> None:
        rnd = ct.get_current_round()
        if rnd % 200 == 1:
            ti, ax = ct.get_global_resources()
            print(
                f"R{rnd} Ti:{ti} Ax:{ax} spawned:{self.spawned} scale:{ct.get_scale_percent():.0f}%",
            )

        max_spawned = min(2 + rnd // 100, 8)
        if self.spawned >= max_spawned:
            return

        pos = ct.get_position()
        candidates = []
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                p = Position(pos.x + dx, pos.y + dy)
                if ct.can_spawn(p):
                    candidates.append(p)
        if candidates:
            sector = SECTOR_DIRS[self.spawned % len(SECTOR_DIRS)]
            sdx, sdy = sector.delta()
            candidates.sort(key=lambda p: -(p.x * sdx + p.y * sdy))
            ct.spawn_builder(candidates[0])
            self.spawned += 1

    # ── Builder ───────────────────────────────────────────────────────

    def _run_builder(self, ct: Controller) -> None:
        pos = ct.get_position()
        if self.core_pos is None:
            self.core_pos = find_core(ct)
        if self.sector is None and self.core_pos:
            self.sector = snap_cardinal(self.core_pos.direction_to(pos))
            if self.sector == Direction.NORTH:
                self.sector = SECTOR_DIRS[ct.get_id() % len(SECTOR_DIRS)]

        match self.phase:
            case Phase.EXPLORE:
                self._explore(ct, pos)
            case Phase.LAY_CONVEYORS:
                self._lay_conveyors(ct, pos)

    # ── Explore ───────────────────────────────────────────────────────

    def _explore(self, ct: Controller, pos: Position) -> None:
        if pos in self.visited:
            self.explore_stale += 1
        else:
            self.explore_stale = 0
        self.visited.add(pos)
        if not self.path or self.path[-1] != pos:
            self.path.append(pos)

        # Build harvester on cardinally-adjacent ore
        if ct.get_action_cooldown() == 0:
            best_ore = None
            best_dir = None
            best_dist = 999999
            for d in CARDINAL:
                check = pos.add(d)
                if in_bounds(ct, check) and ct.can_build_harvester(check):
                    dist = check.distance_squared(self.core_pos) if self.core_pos else 0
                    if dist < best_dist:
                        best_dist = dist
                        best_ore = check
                        best_dir = d
            if best_ore and best_dir:
                ct.build_harvester(best_ore)
                self._start_return(best_dir)
                print(f"Harvester at {best_ore}")
                return

        if ct.get_move_cooldown() > 0:
            return

        # Decide preferred direction
        ore = find_nearest_ore(ct, pos)
        if ore:
            preferred = cardinal_toward(pos, ore)
        elif self.explore_stale > 4:
            # All immediate neighbours visited — scan vision for unvisited tiles
            nearest_unvisited: Position | None = None
            nearest_dist = 999999
            for tile in ct.get_nearby_tiles():
                if tile not in self.visited:
                    d = pos.distance_squared(tile)
                    if d < nearest_dist:
                        nearest_dist = d
                        nearest_unvisited = tile
            if nearest_unvisited:
                # Cross visited ground to reach new territory
                preferred = cardinal_toward(pos, nearest_unvisited)
            else:
                # Truly nothing new in vision range — stop
                return
        elif self.sector:
            preferred = snap_cardinal(self.sector)
        else:
            preferred = Direction.NORTH

        # Score each cardinal direction
        scored: list[tuple[int, Direction]] = []
        for d in CARDINAL:
            target = pos.add(d)
            if not in_bounds(ct, target):
                continue
            score = 0
            if target not in self.visited:
                score += 10
            if d == preferred:
                score += 3
            elif d != preferred.opposite():
                score += 1
            scored.append((score, d))

        scored.sort(key=lambda x: -x[0])
        for _, d in scored:
            if try_move(ct, pos, d):
                return

    # ── Return path ───────────────────────────────────────────────────

    def _start_return(self, harvester_dir: Direction) -> None:
        cleaned = clean_path(self.path)
        self.return_path = list(reversed(cleaned))
        self.return_idx = 0
        self.stuck_turns = 0
        self.harvester_dir = harvester_dir
        self.phase = Phase.LAY_CONVEYORS

    # ── Lay conveyors ─────────────────────────────────────────────────

    def _lay_conveyors(self, ct: Controller, pos: Position) -> None:
        # Advance index to current position
        while self.return_idx < len(self.return_path):
            if self.return_path[self.return_idx] == pos:
                break
            self.return_idx += 1

        # Reached core?
        if self.core_pos and is_on_core(pos, self.core_pos):
            print("Chain complete (core)")
            self._finish_return()
            return

        # Reached an existing friendly conveyor we can feed into?
        if self.return_idx > 0 and tile_has_friendly_conveyor(ct, pos):
            # Check that this conveyor accepts input from the direction we're coming from
            prev_pos = self.return_path[max(0, self.return_idx - 1)]
            if can_feed_into(ct, prev_pos, pos):
                print(f"Chain merged at {pos}")
                self._finish_return()
                return

        if self.return_idx >= len(self.return_path) - 1:
            # End of recorded path — walk toward core directly
            if self.core_pos and try_move_toward(ct, pos, self.core_pos):
                return
            self._finish_return()
            return

        next_pos = self.return_path[self.return_idx + 1]

        # Build conveyor at current position
        if ct.get_action_cooldown() == 0 and not (
            self.core_pos and is_on_core(pos, self.core_pos)
        ):
            conv_dir = cardinal_toward(pos, next_pos)

            # First conveyor must not face toward the harvester
            if self.return_idx == 0 and conv_dir == self.harvester_dir:
                for alt in cardinal_priority(conv_dir):
                    if alt != self.harvester_dir:
                        conv_dir = alt
                        break

            # Destroy existing building (road from exploration)
            bid = ct.get_tile_building_id(pos)
            if bid is not None and ct.can_destroy(pos):
                ct.destroy(pos)

            if ct.can_build_conveyor(pos, conv_dir):
                ct.build_conveyor(pos, conv_dir)

        # Move toward next position
        if ct.get_move_cooldown() > 0:
            return

        d = pos.direction_to(next_pos)
        if try_move(ct, pos, d, build_road=True):
            self.return_idx += 1
            self.stuck_turns = 0
        else:
            self.stuck_turns += 1
            if self.stuck_turns <= 3:
                return  # wait for blocker to move
            for alt in cardinal_priority(cardinal_toward(pos, next_pos)):
                if try_move(ct, pos, alt, build_road=True):
                    self.stuck_turns = 0
                    return
            if self.stuck_turns > 10:
                self.return_idx += 1
                self.stuck_turns = 0

    def _finish_return(self) -> None:
        self.phase = Phase.EXPLORE
        self.path = []
        self.return_path = []
        self.return_idx = 0
        self.stuck_turns = 0
        self.explore_stale = 0
        # Note: self.visited is NOT cleared — persists across cycles
