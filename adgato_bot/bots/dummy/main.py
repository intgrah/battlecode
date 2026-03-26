"""Dummy bot for testing - random walk with harvesters, no conveyors.

Deliberately weak: spawns a few builders that wander, build harvesters
on ore they find, and lay roads. No conveyor chains, no turrets.
Exists so v5 has something to run against.
"""

import random

from cambc import Controller, Direction, EntityType, Environment, Position

DIRS = [d for d in Direction if d != Direction.CENTRE]


class Player:
    def __init__(self):
        self.spawned = 0

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            if self.spawned < 3:
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

        elif etype == EntityType.BUILDER_BOT:
            pos = ct.get_position()
            # Try to build a sentinel on an adjacent tile

            # Random walk with roads
            if ct.get_move_cooldown() == 0:
                order = list(DIRS)
                random.shuffle(order)
                for d in order:
                    pos = ct.get_position()
                    if ct.can_move(d):
                        if ct.can_destroy(pos):
                            ct.destroy(pos)
                        ct.move(d)
                        print(f"Build at move source after move: {ct.can_build_road(pos)}")
                        return
                    target = pos.add(d)
                    if ct.get_action_cooldown() == 0 and ct.can_build_road(target):
                        ct.build_road(target)
                        if ct.can_move(d):
                            ct.move(d)
                            return

        elif etype == EntityType.SENTINEL:
            self._test_sentinel_marker(ct)

    def _test_sentinel_marker(self, ct: Controller) -> None:
        """Sentinel places a marker as far away as possible with a random 32-bit value."""
        pos = ct.get_position()
        tiles = ct.get_nearby_tiles()
        # Sort by distance descending, pick the farthest tile we can place a marker on
        tiles.sort(key=lambda t: pos.distance_squared(t), reverse=True)
        for tile in tiles:
            if ct.can_place_marker(tile):
                value = random.getrandbits(32)
                ct.place_marker(tile, value)
                return
