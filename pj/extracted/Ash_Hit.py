"""Starter bot - a simple example to demonstrate usage of the Controller API.

Each unit gets its own Player instance; the engine calls run() once per round.
Use Controller.get_entity_type() to branch on what kind of unit you are.

This bot:
  - Core: spawns up to 3 builder bots on random adjacent tiles
  - Builder bot: builds a harvester on any adjacent ore tile, then moves in a
    random direction (laying a road first so the tile is passable), and places
    a marker recording the current round number
"""

import random

from cambc import Controller, Direction, EntityType, Environment, Position

# non-centre directions
DIRECTIONS = [Direction.NORTH, Direction.EAST, Direction.WEST, Direction.SOUTH]


def is_in_bound(p: Position, ct: Controller):
    return (
        p.x >= 0 and p.y >= 0 and p.x < ct.get_map_width() and p.y < ct.get_map_height()
    )


class Player:
    def __init__(self) -> None:
        self.player = None

    def run(self, ct: Controller) -> None:
        if self.player is None:
            etype = ct.get_entity_type()
            if etype == EntityType.CORE:
                self.player = Core()
            elif etype == EntityType.BUILDER_BOT:
                self.player = BuilderBot()
        self.player.run(ct)


class Core:
    def __init__(self) -> None:
        self.num_spawned = 0

    def run(self, ct: Controller) -> None:
        if self.num_spawned < 3:
            # if we haven't spawned 3 builder bots yet, try to spawn one on a random tile
            spawn_pos = ct.get_position().add(random.choice(DIRECTIONS))
            if ct.can_spawn(spawn_pos):
                ct.spawn_builder(spawn_pos)
                self.num_spawned += 1
        if ct.get_global_resources()[0] > 1000 and (
            ct.get_current_round() % 100 == 0 or (ct.get_current_round() > 500)
        ):
            spawn_pos = ct.get_position().add(random.choice(DIRECTIONS))
            if ct.can_spawn(spawn_pos):
                ct.spawn_builder(spawn_pos)
                self.num_spawned += 1
        if ct.get_current_round() in [50, 100, 150]:
            spawn_pos = ct.get_position().add(random.choice(DIRECTIONS))
            if ct.can_spawn(spawn_pos):
                ct.spawn_builder(spawn_pos)
                self.num_spawned += 1


class BuilderBot:
    def __init__(self) -> None:
        self.path = []
        self.state = "searching ore"
        self.spawn_round = 0
        self.spawn_pos = None

    def run(self, ct: Controller) -> None:
        print(
            f"BuilderBot at {ct.get_position()} in state {self.state} with path {self.path}",
        )
        if self.spawn_round == 0:
            self.spawn_round = ct.get_current_round()
            self.spawn_pos = ct.get_position()

        if self.spawn_round > 200:
            # destructive mode
            building_id = ct.get_tile_building_id(ct.get_position())
            if (
                building_id is not None
                and ct.get_entity_type(building_id) == EntityType.CONVEYOR
                and ct.get_team(building_id) != ct.get_team()
                and (
                    ct.get_stored_resource(building_id) is not None
                    or ct.get_current_round() - self.spawn_round > 100
                )
            ):
                ct.self_destruct()
                return
            move_dir = [d for d in Direction if d != Direction.CENTRE]
            move_pos = [ct.get_position().add(d) for d in move_dir]
            move_pos = [
                x
                for x in move_pos
                if is_in_bound(x, ct) and ct.get_tile_env(x) != Environment.WALL
            ]
            move_weights = []

            for pos in move_pos:
                weight = 0
                building_id = ct.get_tile_building_id(pos)
                if (
                    building_id is not None
                    and ct.get_entity_type(building_id) == EntityType.CONVEYOR
                    and ct.get_team(building_id) != ct.get_team()
                ):
                    weight += 100
                    if ct.get_stored_resource(building_id) is not None:
                        weight += 100
                move_weights.append(weight)

            # Also check for enemy conveyors in vision and increase weights towards them
            nearby_buildings = ct.get_nearby_buildings()
            for building_id in nearby_buildings:
                if (
                    ct.get_entity_type(building_id) == EntityType.CONVEYOR
                    and ct.get_team(building_id) != ct.get_team()
                ):
                    building_pos = ct.get_position(building_id)
                    enemy_dir = ct.get_position().direction_to(building_pos)
                    if enemy_dir in move_dir:
                        dir_index = move_dir.index(enemy_dir)
                        if dir_index < len(move_weights):
                            move_weights[dir_index] += 50

            # choose a move based on the weights
            total_weight = sum(move_weights)
            if total_weight == 0:
                dest = random.choice(move_pos)
            else:
                r = random.uniform(0, total_weight)
                upto = 0
                dest = move_pos[0]
                for i, w in enumerate(move_weights):
                    if upto + w >= r:
                        dest = move_pos[i]
                        break
                    upto += w

            dir: Direction = ct.get_position().direction_to(dest)
            if ct.can_build_road(dest):
                ct.build_road(dest)
            if ct.can_move(dir):
                ct.move(dir)
                building_id = ct.get_tile_building_id(ct.get_position())
                if (
                    building_id is not None
                    and ct.get_entity_type(building_id) == EntityType.CONVEYOR
                    and ct.get_team(building_id) != ct.get_team()
                    and (
                        ct.get_stored_resource(building_id) is not None
                        or ct.get_current_round() - self.spawn_round > 100
                    )
                ):
                    ct.self_destruct()
            return

        if self.state == "searching ore":
            if self.path == []:
                self.path.append(ct.get_position())
            for d in DIRECTIONS:
                check_pos = ct.get_position().add(d)
                if not is_in_bound(check_pos, ct):
                    continue
                if (
                    ct.get_tile_env(check_pos) == Environment.ORE_AXIONITE
                    or ct.get_tile_env(check_pos) == Environment.ORE_TITANIUM
                ) and ct.get_entity_type(
                    ct.get_tile_building_id(check_pos),
                ) != EntityType.HARVESTER:
                    if ct.can_build_harvester(check_pos):
                        ct.build_harvester(check_pos)
                        self.state = "building conveyor"
                    return

            move_dir = DIRECTIONS
            move_pos = [ct.get_position().add(d) for d in move_dir]

            move_pos = [
                x
                for x in move_pos
                if is_in_bound(x, ct) and ct.get_tile_env(x) != Environment.WALL
            ]
            move_pos_prefered = [x for x in move_pos if ct.is_tile_empty(x)]
            dest: Position = ct.get_position()
            if len(move_pos_prefered) > 0:
                # there is some move to new square
                dest = random.choice(move_pos_prefered)

            else:
                dest = random.choice(move_pos)
                if dest in self.path:
                    self.path = self.path[0 : self.path.index(dest)]

            dir: Direction = None
            dir = ct.get_position().direction_to(dest)

            if ct.get_global_resources()[0] < ct.get_road_cost()[0]:
                return

            if ct.can_build_road(dest):
                ct.build_road(dest)
            if ct.can_move(dir):
                ct.move(dir)
                self.path.append(dest)

        elif self.state == "building conveyor":
            if ct.get_global_resources()[0] < ct.get_conveyor_cost()[0]:
                return
            last = self.path.pop()
            if len(self.path) == 0:
                self.state = "searching ore"
                self.path = []
                return
            dir = ct.get_position().direction_to(self.path[-1])
            old_pos = ct.get_position()
            if ct.can_move(dir):
                ct.move(dir)
                if ct.can_destroy(old_pos):
                    ct.destroy(old_pos)
                if ct.can_build_conveyor(old_pos, dir):
                    ct.build_conveyor(old_pos, dir)

                if ct.get_entity_type(ct.get_tile_building_id(ct.get_position())) in [
                    EntityType.CONVEYOR,
                    EntityType.CORE,
                ]:
                    self.state = "searching ore"
                    self.path = []
            else:
                self.path.append(last)
