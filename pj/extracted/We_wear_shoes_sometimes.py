"""Spam bot - A starter which eventually starts kamikazeing builder bots on the enemy

- Starts by spawning 3 builder bots, and they walk around building harvesters and conveyors.
- Once we have ample resources, the core will start producing more and more bots, and they will start kamikazeing
"""

import random

from cambc import Controller, Direction, EntityType

AMPLE_RESOURCES = 1000

# non-centre directions
DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]

opposite_direction = {
    Direction.NORTH: Direction.SOUTH,
    Direction.SOUTH: Direction.NORTH,
    Direction.EAST: Direction.WEST,
    Direction.WEST: Direction.EAST,
    Direction.NORTHEAST: Direction.SOUTHWEST,
    Direction.NORTHWEST: Direction.SOUTHEAST,
    Direction.SOUTHEAST: Direction.NORTHWEST,
    Direction.SOUTHWEST: Direction.NORTHEAST,
    Direction.CENTRE: Direction.CENTRE,
}

class Player:
    def __init__(self) -> None:
        self.num_spawned = 0 # number of builder bots spawned so far (core)

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            if self.num_spawned < 3 or ct.get_global_resources()[0] > AMPLE_RESOURCES:
                # if we haven't spawned 3 builder bots yet, try to spawn one on a random tile
                spawn_pos = ct.get_position().add(random.choice(DIRECTIONS))
                if ct.can_spawn(spawn_pos):
                    ct.spawn_builder(spawn_pos)
                    self.num_spawned += 1
        elif etype == EntityType.BUILDER_BOT:
            # if we are adjacent to an ore tile, build a harvester on it
            for d in Direction:
                check_pos = ct.get_position().add(d)
                if ct.can_build_harvester(check_pos):
                    ct.build_harvester(check_pos)
                    break

            # move in a random direction
            move_dir = random.choice(DIRECTIONS)
            move_pos = ct.get_position().add(move_dir)
            # we need to place a conveyor or road to stand on, before we can move onto a tile
            if ct.can_build_conveyor(move_pos, opposite_direction[move_dir]):
                ct.build_conveyor(move_pos, opposite_direction[move_dir])
            if ct.can_move(move_dir):
                ct.move(move_dir)

            # place a marker on an adjacent tile with the current round number
            marker_pos = ct.get_position().add(random.choice(DIRECTIONS))
            if ct.can_place_marker(marker_pos):
                ct.place_marker(marker_pos, ct.get_current_round())

            # if we have ample resources, start kamikazeing
            if ct.get_tile_building_id(ct.get_position()) is not None and ct.get_team(ct.get_tile_building_id(ct.get_position())) != ct.get_team(ct.get_id()) and ct.get_entity_type(ct.get_tile_building_id(ct.get_position())) == EntityType.CONVEYOR and ct.get_stored_resource(ct.get_tile_building_id(ct.get_position())) is not None:
                print(f"Kamikazeing on tile with {ct.get_stored_resource(ct.get_tile_building_id(ct.get_position()))} resources on turn {ct.get_current_round()}")
                ct.self_destruct()
