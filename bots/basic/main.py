import random

from cambc import Controller, Direction, EntityType, Environment, Position

DIRS = [d for d in Direction if d != Direction.CENTRE]

INITIAL_BUILDERS = 3
MAX_HARVESTERS = 3
ATTACK_ROUND = 400

MARKER_ENEMY_SPOTTED = 0xE000_0000
MARKER_ENEMY_MASK = 0xE000_0000
MARKER_POS_MASK = 0x0FFF_0FFF


def encode_pos(pos: Position) -> int:
    return (pos.x & 0xFFF) | ((pos.y & 0xFFF) << 16)


def decode_pos(val: int) -> Position:
    return Position(val & 0xFFF, (val >> 16) & 0xFFF)


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


def find_nearest_enemy(ct: Controller) -> Position | None:
    my_team = ct.get_team()
    pos = ct.get_position()
    best = None
    best_dist = 999999
    for eid in ct.get_nearby_entities():
        if ct.get_team(eid) != my_team:
            epos = ct.get_position(eid)
            d = pos.distance_squared(epos)
            if d < best_dist:
                best_dist = d
                best = epos
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


def move_toward_building_conveyors(
    ct: Controller, target: Position, core_pos: Position,
) -> bool:
    pos = ct.get_position()
    d = toward(pos, target)
    for cd in [d, d.rotate_left(), d.rotate_right(),
               d.rotate_left().rotate_left(), d.rotate_right().rotate_right()]:
        next_pos = pos.add(cd)
        conv_dir = toward(next_pos, core_pos)
        bid = ct.get_tile_building_id(next_pos) if in_bounds(ct, next_pos) else None
        if bid is not None and ct.get_entity_type(bid) == EntityType.ROAD and ct.can_destroy(next_pos):
            ct.destroy(next_pos)
        if ct.can_build_conveyor(next_pos, conv_dir):
            ct.build_conveyor(next_pos, conv_dir)
        elif ct.can_build_road(next_pos):
            ct.build_road(next_pos)
        if ct.can_move(cd):
            ct.move(cd)
            return True
    return False


def read_enemy_markers(ct: Controller) -> Position | None:
    for tile in ct.get_nearby_tiles():
        bid = ct.get_tile_building_id(tile)
        if bid is None:
            continue
        if ct.get_entity_type(bid) != EntityType.MARKER:
            continue
        if ct.get_team(bid) != ct.get_team():
            continue
        val = ct.get_marker_value(bid)
        if val & MARKER_ENEMY_MASK == MARKER_ENEMY_SPOTTED:
            return decode_pos(val & MARKER_POS_MASK)
    return None


def write_enemy_marker(ct: Controller, enemy_pos: Position) -> None:
    pos = ct.get_position()
    val = MARKER_ENEMY_SPOTTED | encode_pos(enemy_pos)
    for d in Direction:
        tile = pos.add(d)
        if ct.can_place_marker(tile):
            ct.place_marker(tile, val)
            return


def guess_enemy_core(ct: Controller, core_pos: Position) -> Position:
    w = ct.get_map_width()
    h = ct.get_map_height()
    cx, cy = w // 2, h // 2
    dx = cx - core_pos.x
    dy = cy - core_pos.y
    gx = max(0, min(w - 1, core_pos.x + 2 * dx))
    gy = max(0, min(h - 1, core_pos.y + 2 * dy))
    return Position(gx, gy)


# --- Core ---


class CoreBot:
    def __init__(self) -> None:
        self.num_spawned = 0
        self.enemy_pos: Position | None = None

    def run(self, ct: Controller) -> None:
        core_pos = ct.get_position()
        ti, _ax = ct.get_global_resources()
        rnd = ct.get_current_round()

        enemy_from_markers = read_enemy_markers(ct)
        if enemy_from_markers is not None:
            self.enemy_pos = enemy_from_markers

        bot_cost = ct.get_builder_bot_cost()[0]

        if rnd < ATTACK_ROUND:
            should_spawn = self.num_spawned < INITIAL_BUILDERS and ti >= bot_cost + 100
        else:
            should_spawn = ti >= bot_cost * 3

        if should_spawn:
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
        self.ore_target: Position | None = None
        self.role = "economy"

    def run(self, ct: Controller) -> None:
        rnd = ct.get_current_round()

        if self.core_pos is None:
            for eid in ct.get_nearby_entities():
                if ct.get_entity_type(eid) == EntityType.CORE and ct.get_team(eid) == ct.get_team():
                    self.core_pos = ct.get_position(eid)
                    break

        enemy = find_nearest_enemy(ct)
        if enemy is not None:
            write_enemy_marker(ct, enemy)

        if self.enemy_core is None:
            for eid in ct.get_nearby_entities():
                if ct.get_entity_type(eid) == EntityType.CORE and ct.get_team(eid) != ct.get_team():
                    self.enemy_core = ct.get_position(eid)

        if self.enemy_core is None:
            marker_enemy = read_enemy_markers(ct)
            if marker_enemy is not None:
                self.enemy_core = marker_enemy

        if self.role == "economy" and rnd >= ATTACK_ROUND:
            self.role = "attacker"

        if self.role == "attacker":
            self._run_attacker(ct)
        else:
            self._run_economy(ct)

    def _run_economy(self, ct: Controller) -> None:
        ore_adj = adjacent_ore(ct)
        if ore_adj is not None and ct.can_build_harvester(ore_adj):
            ct.build_harvester(ore_adj)
            self.harvesters_built += 1
            self.ore_target = None
            return

        if self.harvesters_built < MAX_HARVESTERS:
            if self.ore_target is None:
                self.ore_target = nearest_ore(ct)
            if self.ore_target is not None and self.core_pos is not None:
                move_toward_building_conveyors(ct, self.ore_target, self.core_pos)
                return

        try_move_random(ct)

    def _run_attacker(self, ct: Controller) -> None:
        pos = ct.get_position()
        target = self.enemy_core
        if target is None and self.core_pos is not None:
            target = guess_enemy_core(ct, self.core_pos)
        if target is None:
            try_move_random(ct)
            return

        dist = pos.distance_squared(target)

        if dist <= 2:
            facing = toward(pos, target)
            for d in Direction:
                tile = pos.add(d)
                if ct.can_build_gunner(tile, facing):
                    ct.build_gunner(tile, facing)
                    return
            ct.self_destruct()
            return

        if dist <= 13:
            facing = toward(pos, target)
            for d in Direction:
                tile = pos.add(d)
                if ct.can_build_gunner(tile, facing):
                    ct.build_gunner(tile, facing)
                    return

        try_move_toward(ct, target)


# --- Turret ---


class TurretBot:
    def run(self, ct: Controller) -> None:
        try:
            target = ct.get_gunner_target()
            if target is not None and ct.can_fire(target):
                ct.fire(target)
        except Exception:
            pass


# --- Player ---


class Player:
    def __init__(self) -> None:
        self.core = CoreBot()
        self.builder = BuilderBot()
        self.turret = TurretBot()

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            self.core.run(ct)
        elif etype == EntityType.BUILDER_BOT:
            self.builder.run(ct)
        elif etype in (EntityType.GUNNER, EntityType.SENTINEL, EntityType.BREACH):
            self.turret.run(ct)
