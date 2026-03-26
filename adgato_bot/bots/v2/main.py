"""v2 bot - economy with connected conveyor chains.

Strategy:
  - Core: spawn builders steadily
  - Builders: explore for ore, build harvesters, then lay a conveyor chain
    back to the core following the recorded path.
  - Conveyors are cardinal-only (N/E/S/W), so the return path uses cardinal
    moves. Diagonal steps are split into two cardinal steps.
"""

import random
from cambc import Controller, Direction, EntityType, Environment, Position

CARDINAL_DIRS = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]
ALL_DIRS = [d for d in Direction if d != Direction.CENTRE]


def snap_to_cardinal(d: Direction) -> Direction:
    """Snap a direction to the nearest cardinal direction."""
    mapping = {
        Direction.NORTH: Direction.NORTH,
        Direction.SOUTH: Direction.SOUTH,
        Direction.EAST: Direction.EAST,
        Direction.WEST: Direction.WEST,
        Direction.NORTHEAST: Direction.EAST,
        Direction.NORTHWEST: Direction.NORTH,
        Direction.SOUTHEAST: Direction.SOUTH,
        Direction.SOUTHWEST: Direction.WEST,
        Direction.CENTRE: Direction.NORTH,
    }
    return mapping[d]


def cardinal_steps(from_pos: Position, to_pos: Position) -> list[Direction]:
    """Return 1-2 cardinal directions to get from from_pos toward to_pos."""
    dx = to_pos.x - from_pos.x
    dy = to_pos.y - from_pos.y
    steps = []
    if dx > 0: steps.append(Direction.EAST)
    elif dx < 0: steps.append(Direction.WEST)
    if dy > 0: steps.append(Direction.SOUTH)
    elif dy < 0: steps.append(Direction.NORTH)
    return steps if steps else [Direction.NORTH]


class Player:
    def __init__(self):
        # Core
        self.spawned = 0
        # Builder
        self.core_pos: Position | None = None
        self.phase = "explore"
        self.path: list[Position] = []  # positions visited during explore
        self.return_path: list[Position] = []  # reversed path for laying conveyors
        self.return_idx = 0

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            self._run_core(ct)
        elif etype == EntityType.BUILDER_BOT:
            self._run_builder(ct)

    # ── Core ──────────────────────────────────────────────────────────

    def _run_core(self, ct: Controller) -> None:
        round_num = ct.get_current_round()
        if round_num % 200 == 1:
            ti, ax = ct.get_global_resources()
            print(f"R{round_num} Ti:{ti} Ax:{ax} spawned:{self.spawned} scale:{ct.get_scale_percent():.0f}%")

        max_spawned = min(2 + round_num // 100, 8)
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
            ct.spawn_builder(random.choice(candidates))
            self.spawned += 1

    # ── Builder ───────────────────────────────────────────────────────

    def _run_builder(self, ct: Controller) -> None:
        pos = ct.get_position()
        if self.core_pos is None:
            self.core_pos = self._find_core(ct)

        if self.phase == "explore":
            self._explore(ct, pos)
        elif self.phase == "lay_conveyors":
            self._lay_conveyors(ct, pos)
        elif self.phase == "idle":
            self._explore(ct, pos)

    def _find_core(self, ct: Controller) -> Position | None:
        my_team = ct.get_team()
        for eid in ct.get_nearby_buildings():
            if ct.get_entity_type(eid) == EntityType.CORE and ct.get_team(eid) == my_team:
                return ct.get_position(eid)
        return None

    def _in_bounds(self, ct: Controller, p: Position) -> bool:
        return 0 <= p.x < ct.get_map_width() and 0 <= p.y < ct.get_map_height()

    # ── Explore phase ─────────────────────────────────────────────────

    def _explore(self, ct: Controller, pos: Position) -> None:
        # Record path
        if not self.path or self.path[-1] != pos:
            self.path.append(pos)

        # Check for adjacent ore → build harvester
        if ct.get_action_cooldown() == 0:
            for d in ALL_DIRS:
                check = pos.add(d)
                if self._in_bounds(ct, check) and ct.can_build_harvester(check):
                    ct.build_harvester(check)
                    print(f"Built harvester at {check}, preparing return path")
                    self._prepare_return()
                    return

        # Move: prefer cardinal directions, aim for nearest visible ore
        if ct.get_move_cooldown() > 0:
            return

        target_dir = self._find_ore_direction(ct, pos)
        if target_dir is None and self.core_pos:
            # Wander away from core
            away = self.core_pos.direction_to(pos)
            target_dir = snap_to_cardinal(away) if away != Direction.CENTRE else random.choice(CARDINAL_DIRS)

        if target_dir is None:
            target_dir = random.choice(CARDINAL_DIRS)

        # Try the target direction, then alternatives
        for d in self._direction_priority(target_dir):
            move_pos = pos.add(d)
            if not self._in_bounds(ct, move_pos):
                continue
            if ct.get_action_cooldown() == 0 and ct.can_build_road(move_pos):
                ct.build_road(move_pos)
            if ct.can_move(d):
                ct.move(d)
                return

    def _find_ore_direction(self, ct: Controller, pos: Position) -> Direction | None:
        """Find nearest unharvested ore tile and return cardinal direction toward it."""
        best_ore = None
        best_dist = 999999
        for tile in ct.get_nearby_tiles():
            env = ct.get_tile_env(tile)
            if env in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE):
                bid = ct.get_tile_building_id(tile)
                if bid is None:
                    d = pos.distance_squared(tile)
                    if d < best_dist:
                        best_dist = d
                        best_ore = tile
        if best_ore:
            return snap_to_cardinal(pos.direction_to(best_ore))
        return None

    def _direction_priority(self, preferred: Direction) -> list[Direction]:
        """Return directions to try: preferred first, then rotations, avoiding backtrack."""
        result = [preferred]
        # Add adjacent cardinal directions
        left = preferred.rotate_left()
        right = preferred.rotate_right()
        # snap rotations to cardinal (rotate from cardinal gives diagonal)
        for d in [left, right]:
            snapped = snap_to_cardinal(d)
            if snapped not in result:
                result.append(snapped)
        # Add remaining cardinals
        for d in CARDINAL_DIRS:
            if d not in result:
                result.append(d)
        return result

    # ── Return phase: lay conveyors back to core ─────────────────────

    def _prepare_return(self) -> None:
        """Build a cardinal-only return path from current position to core."""
        # Simplify path: deduplicate consecutive identical positions
        simplified = []
        for p in self.path:
            if not simplified or simplified[-1] != p:
                simplified.append(p)

        # The return path is the reverse
        self.return_path = list(reversed(simplified))
        self.return_idx = 0
        self.phase = "lay_conveyors"

    def _lay_conveyors(self, ct: Controller, pos: Position) -> None:
        # Find where we are in the return path
        # Skip positions we've already passed
        while self.return_idx < len(self.return_path) - 1:
            if self.return_path[self.return_idx] == pos:
                break
            self.return_idx += 1

        if self.return_idx >= len(self.return_path) - 1:
            # We've reached the core (or close enough)
            print(f"Conveyor chain complete, going idle")
            self.phase = "idle"
            self.path = []
            return

        # Next position in return path (closer to core)
        next_pos = self.return_path[self.return_idx + 1]

        # Build conveyor at current position pointing toward next_pos
        if ct.get_action_cooldown() == 0:
            # Determine cardinal direction(s) toward next_pos
            steps = cardinal_steps(pos, next_pos)
            conv_dir = steps[0]

            # Check if we're on core tiles — don't build there
            core_bid = ct.get_tile_building_id(pos)
            if core_bid is not None:
                etype = ct.get_entity_type(core_bid)
                if etype == EntityType.CORE:
                    # On core, just move on
                    self.return_idx += 1
                    self.phase = "idle"
                    self.path = []
                    return

            # Destroy existing building at current tile (road from exploration)
            if core_bid is not None and ct.can_destroy(pos):
                ct.destroy(pos)

            # Build conveyor
            if ct.can_build_conveyor(pos, conv_dir):
                ct.build_conveyor(pos, conv_dir)

        # Move toward next position
        if ct.get_move_cooldown() == 0:
            d = pos.direction_to(next_pos)
            # Build road on next tile if needed (so we can walk there)
            next_tile = pos.add(d)
            # We might need a road if the next tile isn't passable yet
            if ct.get_action_cooldown() == 0 and self._in_bounds(ct, next_tile):
                if ct.can_build_road(next_tile):
                    ct.build_road(next_tile)

            if ct.can_move(d):
                ct.move(d)
                self.return_idx += 1
            else:
                # Try cardinal alternatives
                for alt in CARDINAL_DIRS:
                    alt_pos = pos.add(alt)
                    if not self._in_bounds(ct, alt_pos):
                        continue
                    if ct.get_action_cooldown() == 0 and ct.can_build_road(alt_pos):
                        ct.build_road(alt_pos)
                    if ct.can_move(alt):
                        ct.move(alt)
                        break
