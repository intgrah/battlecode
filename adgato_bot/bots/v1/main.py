"""v1 bot - simple economy-first strategy.

Strategy:
  - Core: spawn builders steadily (up to a cap based on round number)
  - Builder bots: find ore, build harvesters, lay conveyor lines back toward core
  - No turrets yet -- pure economy focus
"""

import random

from cambc import Controller, Direction, EntityType, Environment, Position, GameConstants

DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]


class Player:
    def __init__(self):
        self.spawned = 0
        self.has_target = False
        self.target: Position | None = None
        self.returning = False

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            self._run_core(ct)
        elif etype == EntityType.BUILDER_BOT:
            self._run_builder(ct)

    # ── Core ──────────────────────────────────────────────────────────

    def _run_core(self, ct: Controller) -> None:
        round_num = ct.get_current_round()
        if round_num % 100 == 1:
            ti, ax = ct.get_global_resources()
            print(f"R{round_num} Ti:{ti} Ax:{ax} spawned:{self.spawned} scale:{ct.get_scale_percent():.0f}%")

        # Spawn more builders over time, but not too fast
        max_spawned = min(3 + round_num // 50, 12)
        if self.spawned >= max_spawned:
            return

        # Try to spawn on a passable tile, else any spawnable tile
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
        core_pos = self._find_core(ct)

        # Priority 1: build harvesters on adjacent ore
        if ct.get_action_cooldown() == 0:
            for d in DIRECTIONS:
                check = pos.add(d)
                if ct.can_build_harvester(check):
                    ct.build_harvester(check)
                    return

        # Priority 2: build conveyors pointing toward core if we see a harvester
        #             that doesn't have a conveyor adjacent on its core-side
        if ct.get_action_cooldown() == 0 and core_pos:
            self._try_build_conveyor_near_harvester(ct, pos, core_pos)

        # Priority 3: explore -- move toward ore if we can see some, else wander
        self._explore(ct, pos, core_pos)

    def _find_core(self, ct: Controller) -> Position | None:
        """Find our core's position."""
        my_team = ct.get_team()
        for eid in ct.get_nearby_buildings():
            if ct.get_entity_type(eid) == EntityType.CORE and ct.get_team(eid) == my_team:
                return ct.get_position(eid)
        return None

    def _in_bounds(self, ct: Controller, p: Position) -> bool:
        return 0 <= p.x < ct.get_map_width() and 0 <= p.y < ct.get_map_height()

    def _try_build_conveyor_near_harvester(self, ct: Controller, pos: Position, core_pos: Position) -> None:
        """If adjacent to a tile that could use a conveyor toward core, build one."""
        for d in DIRECTIONS:
            build_pos = pos.add(d)
            if not self._in_bounds(ct, build_pos):
                continue
            if not ct.is_tile_empty(build_pos):
                continue
            # Build conveyor pointing toward core
            conv_dir = build_pos.direction_to(core_pos)
            if conv_dir == Direction.CENTRE:
                continue
            if ct.can_build_conveyor(build_pos, conv_dir):
                ct.build_conveyor(build_pos, conv_dir)
                return

    def _explore(self, ct: Controller, pos: Position, core_pos: Position | None) -> None:
        """Move toward nearest visible ore, or wander randomly."""
        if ct.get_move_cooldown() > 0:
            return

        # Look for ore tiles
        best_ore = None
        best_dist = 999999
        for tile in ct.get_nearby_tiles():
            env = ct.get_tile_env(tile)
            if env in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE):
                # Only interested if no harvester already there
                bid = ct.get_tile_building_id(tile)
                if bid is None:
                    d = pos.distance_squared(tile)
                    if d < best_dist:
                        best_dist = d
                        best_ore = tile

        if best_ore:
            direction = pos.direction_to(best_ore)
        else:
            # Wander away from core to explore
            if core_pos:
                direction = core_pos.direction_to(pos)
                if direction == Direction.CENTRE:
                    direction = random.choice(DIRECTIONS)
            else:
                direction = random.choice(DIRECTIONS)

        # Try to move, building a road if needed
        move_pos = pos.add(direction)
        if ct.get_action_cooldown() == 0 and ct.can_build_road(move_pos):
            ct.build_road(move_pos)
        if ct.can_move(direction):
            ct.move(direction)
        else:
            # Try adjacent directions
            for alt in [direction.rotate_left(), direction.rotate_right()]:
                alt_pos = pos.add(alt)
                if ct.get_action_cooldown() == 0 and ct.can_build_road(alt_pos):
                    ct.build_road(alt_pos)
                if ct.can_move(alt):
                    ct.move(alt)
                    return
