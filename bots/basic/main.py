import random

from cambc import Controller, Direction, EntityType, Environment, Position

DIRS = [d for d in Direction if d != Direction.CENTRE]
MAX_BUILDERS = 5
MAX_HARVESTERS = 4


# --- Utilities ---


def toward(pos: Position, target: Position) -> Direction:
    return pos.direction_to(target)


def in_bounds(ct: Controller, pos: Position) -> bool:
    return 0 <= pos.x < ct.get_map_width() and 0 <= pos.y < ct.get_map_height()


def adjacent_ore(ct: Controller) -> Position | None:
    pos = ct.get_position()
    for d in Direction:
        tile = pos.add(d)
        if not in_bounds(ct, tile):
            continue
        if (
            ct.get_tile_env(tile) in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE)
            and ct.get_tile_building_id(tile) is None
        ):
            return tile
    return None


def nearest_ore(ct: Controller) -> Position | None:
    best = None
    best_dist = 999999
    pos = ct.get_position()
    for tile in ct.get_nearby_tiles():
        if ct.get_tile_env(tile) not in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE):
            continue
        if ct.get_tile_building_id(tile) is not None:
            continue
        d = pos.distance_squared(tile)
        if d < best_dist:
            best_dist = d
            best = tile
    return best


def try_move_toward(ct: Controller, target: Position) -> bool:
    pos = ct.get_position()
    d = toward(pos, target)
    for cd in [d, d.rotate_left(), d.rotate_right(),
               d.rotate_left().rotate_left(), d.rotate_right().rotate_right()]:
        next_pos = pos.add(cd)
        if ct.can_build_road(next_pos):
            ct.build_road(next_pos)
        if ct.can_move(cd):
            ct.move(cd)
            return True
    return False


def try_move_random(ct: Controller) -> bool:
    dirs = list(DIRS)
    random.shuffle(dirs)
    pos = ct.get_position()
    for d in dirs:
        next_pos = pos.add(d)
        if ct.can_build_road(next_pos):
            ct.build_road(next_pos)
        if ct.can_move(d):
            ct.move(d)
            return True
    return False


# --- Core ---


class CoreBot:
    def __init__(self) -> None:
        self.num_spawned = 0

    def run(self, ct: Controller) -> None:
        core_pos = ct.get_position()
        ti, _ax = ct.get_global_resources()
        bot_cost = ct.get_builder_bot_cost()[0]

        if self.num_spawned < MAX_BUILDERS and ti >= bot_cost + 80:
            dirs = list(DIRS)
            random.shuffle(dirs)
            for d in dirs:
                spawn_pos = core_pos.add(d)
                if ct.can_spawn(spawn_pos):
                    ct.spawn_builder(spawn_pos)
                    self.num_spawned += 1
                    break


# --- Builder Bot ---


class BuilderBot:
    def __init__(self) -> None:
        self.core_pos: Position | None = None
        self.enemy_core: Position | None = None
        self.harvesters_built = 0
        self.returning = False

    def run(self, ct: Controller) -> None:
        if self.core_pos is None:
            for eid in ct.get_nearby_entities():
                if ct.get_entity_type(eid) == EntityType.CORE and ct.get_team(eid) == ct.get_team():
                    self.core_pos = ct.get_position(eid)
                    break

        if self.enemy_core is None:
            for eid in ct.get_nearby_entities():
                if ct.get_entity_type(eid) == EntityType.CORE and ct.get_team(eid) != ct.get_team():
                    self.enemy_core = ct.get_position(eid)

        if self.returning and self.core_pos is not None:
            self._return_with_conveyors(ct)
            return

        ore_adj = adjacent_ore(ct)
        if ore_adj is not None and ct.can_build_harvester(ore_adj):
            ct.build_harvester(ore_adj)
            self.harvesters_built += 1
            self.returning = True
            return

        if self.harvesters_built < MAX_HARVESTERS:
            ore = nearest_ore(ct)
            if ore is not None:
                try_move_toward(ct, ore)
                return

        try_move_random(ct)

    def _return_with_conveyors(self, ct: Controller) -> None:
        pos = ct.get_position()

        if self.core_pos is None:
            self.returning = False
            return

        if pos.distance_squared(self.core_pos) <= 8:
            d = toward(pos, self.core_pos)
            if ct.can_build_conveyor(pos, d):
                ct.build_conveyor(pos, d)
            self.returning = False
            return

        d = toward(pos, self.core_pos)
        for cd in [d, d.rotate_left(), d.rotate_right(),
                   d.rotate_left().rotate_left(), d.rotate_right().rotate_right()]:
            next_pos = pos.add(cd)
            if ct.can_build_road(next_pos):
                ct.build_road(next_pos)
            if ct.can_move(cd):
                if ct.can_build_conveyor(pos, cd):
                    ct.build_conveyor(pos, cd)
                ct.move(cd)
                return

        dirs = list(DIRS)
        random.shuffle(dirs)
        for cd in dirs:
            next_pos = pos.add(cd)
            if ct.can_build_road(next_pos):
                ct.build_road(next_pos)
            if ct.can_move(cd):
                ct.move(cd)
                return

        self.returning = False


# --- Player ---


class Player:
    def __init__(self) -> None:
        self.core = CoreBot()
        self.builder = BuilderBot()

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            self.core.run(ct)
        elif etype == EntityType.BUILDER_BOT:
            self.builder.run(ct)
