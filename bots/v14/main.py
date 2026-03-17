import random

from cambc import Controller, Direction, EntityType, Environment, Position

DIRS = [d for d in Direction if d != Direction.CENTRE]

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

NUM_BUILDERS = 8
RAIDER_IDS = {6, 7}
RAIDER_START = 200
IDLE_BEFORE_RAID = 60
MAX_TOTAL_BUILDERS = 50
RAIDER_SPAWN_INTERVAL = 20
RAIDER_TI_THRESHOLD = 1000

BLOCK_SIZE = 5

# Marker ADT: 2-bit tag in bits 30-31
TAG_ASSIGN = 0 << 30  # sector assignment
TAG_EXPLORED = 1 << 30  # explored block, no ore: bx(4) by(4)
TAG_DEADEND = 2 << 30  # dead end direction: bx(4) by(4) dir(4)
TAG_MASK = 0xC000_0000


def mk_assign(sector: int) -> int:
    return TAG_ASSIGN | (sector & 0xFF)


def mk_explored(bx: int, by: int) -> int:
    return TAG_EXPLORED | ((bx & 0xF) << 4) | (by & 0xF)


def mk_deadend(bx: int, by: int, dir_idx: int) -> int:
    return TAG_DEADEND | ((bx & 0xF) << 8) | ((by & 0xF) << 4) | (dir_idx & 0xF)


def read_marker(ct: Controller, pos: Position) -> int | None:
    bid = ct.get_tile_building_id(pos)
    if bid is None:
        return None
    if ct.get_entity_type(bid) != EntityType.MARKER:
        return None
    if ct.get_team(bid) != ct.get_team():
        return None
    return ct.get_marker_value(bid)


def toward(pos: Position, target: Position) -> Direction:
    return pos.direction_to(target)


def in_bounds(ct: Controller, pos: Position) -> bool:
    return 0 <= pos.x < ct.get_map_width() and 0 <= pos.y < ct.get_map_height()


def is_wall(ct: Controller, pos: Position) -> bool:
    if not in_bounds(ct, pos):
        return True
    return ct.get_tile_env(pos) == Environment.WALL


def is_ore(ct: Controller, pos: Position) -> bool:
    if not in_bounds(ct, pos):
        return False
    return ct.get_tile_env(pos) in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE)


def adjacent_ore(ct: Controller) -> Position | None:
    pos = ct.get_position()
    for d in Direction:
        tile = pos.add(d)
        if not in_bounds(ct, tile):
            continue
        if is_ore(ct, tile) and ct.get_tile_building_id(tile) is None:
            return tile
    return None


def nearest_ore(ct: Controller) -> Position | None:
    best = None
    best_dist = 999999
    pos = ct.get_position()
    for tile in ct.get_nearby_tiles():
        if not is_ore(ct, tile):
            continue
        if ct.get_tile_building_id(tile) is not None:
            continue
        d = pos.distance_squared(tile)
        if d < best_dist:
            best_dist = d
            best = tile
    return best


def scan_explored_blocks(ct: Controller) -> set[tuple[int, int]]:
    explored = set()
    for tile in ct.get_nearby_tiles():
        val = read_marker(ct, tile)
        if val is not None and val & TAG_MASK == TAG_EXPLORED:
            bx = (val >> 4) & 0xF
            by = val & 0xF
            explored.add((bx, by))
    return explored


def find_enemy_infra(ct: Controller) -> Position | None:
    my_team = ct.get_team()
    pos = ct.get_position()
    best = None
    best_dist = 999999
    for eid in ct.get_nearby_entities():
        if ct.get_team(eid) == my_team:
            continue
        etype = ct.get_entity_type(eid)
        if etype in (
            EntityType.CONVEYOR,
            EntityType.HARVESTER,
            EntityType.ARMOURED_CONVEYOR,
            EntityType.SPLITTER,
            EntityType.BRIDGE,
            EntityType.FOUNDRY,
        ):
            epos = ct.get_position(eid)
            d = pos.distance_squared(epos)
            if d < best_dist:
                best_dist = d
                best = epos
    return best


def bugnav_conv(
    ct: Controller,
    target: Position,
    core_pos: Position,
    state: dict,
    *,
    skip_ore: bool = False,
) -> bool:
    return _bugnav(
        ct,
        target,
        state,
        lambda d: _try_step_conv(ct, d, core_pos, skip_ore),
    )


def bugnav_road(ct: Controller, target: Position, state: dict) -> bool:
    return _bugnav(ct, target, state, lambda d: _try_step_road(ct, d))


def _bugnav(ct: Controller, target: Position, state: dict, step_fn) -> bool:
    pos = ct.get_position()
    d = toward(pos, target)
    dist = pos.distance_squared(target)

    if state.get("last_pos") == (pos.x, pos.y):
        state["stuck"] = state.get("stuck", 0) + 1
    else:
        state["stuck"] = 0
    state["last_pos"] = (pos.x, pos.y)

    if state.get("stuck", 0) > 10:
        state["wall_following"] = False
        state["wall_side"] = -state.get("wall_side", 1)
        state["stuck"] = 0

    if not state.get("wall_following"):
        if step_fn(d):
            state["closest"] = min(state.get("closest", 999999), dist)
            return True
        state["wall_following"] = True
        state.setdefault("wall_side", 1)
        state["closest"] = dist

    scan = d
    side = state.get("wall_side", 1)
    for _ in range(8):
        if step_fn(scan):
            new_dist = ct.get_position().distance_squared(target)
            if new_dist < state.get("closest", 999999):
                state["wall_following"] = False
                state["closest"] = new_dist
            return True
        scan = scan.rotate_right() if side == 1 else scan.rotate_left()

    return False


def _try_step_conv(
    ct: Controller,
    d: Direction,
    core_pos: Position,
    skip_ore: bool = False,
) -> bool:
    pos = ct.get_position()
    next_pos = pos.add(d)
    if is_wall(ct, next_pos):
        return False
    if not skip_ore or not is_ore(ct, next_pos):
        conv_dir = d.opposite()
        if ct.can_build_conveyor(next_pos, conv_dir):
            ct.build_conveyor(next_pos, conv_dir)
        elif ct.can_build_road(next_pos):
            ct.build_road(next_pos)
    elif ct.can_build_road(next_pos):
        ct.build_road(next_pos)
    if ct.can_move(d):
        ct.move(d)
        return True
    return False


def _try_step_road(ct: Controller, d: Direction) -> bool:
    pos = ct.get_position()
    next_pos = pos.add(d)
    if is_wall(ct, next_pos):
        return False
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
        rnd = ct.get_current_round()
        bot_cost = ct.get_builder_bot_cost()[0]

        if self.num_spawned < NUM_BUILDERS:
            if ti < bot_cost + ct.get_harvester_cost()[0]:
                return
        elif (
            self.num_spawned >= MAX_TOTAL_BUILDERS
            or rnd < RAIDER_START
            or ti < RAIDER_TI_THRESHOLD
            or rnd % RAIDER_SPAWN_INTERVAL != 0
        ):
            return

        sector = self.num_spawned
        for d in DIRS:
            spawn_pos = core_pos.add(d)
            if ct.can_spawn(spawn_pos):
                ct.spawn_builder(spawn_pos)
                if ct.can_place_marker(spawn_pos):
                    ct.place_marker(spawn_pos, mk_assign(sector))
                self.num_spawned += 1
                return


# --- Builder ---


class BuilderBot:
    def __init__(self) -> None:
        self.core_pos: Position | None = None
        self.sector_dir: Direction | None = None
        self.explore_target: Position | None = None
        self.explore_turns = 0
        self.initialized = False
        self.nav_state: dict = {}
        self.visited_ore: set[tuple[int, int]] = set()
        self.has_income = False
        self.last_ti = 0
        self.builder_id = 0
        self.raiding = False
        self.turns_without_ore = 0
        self.placed_marker_this_turn = False

    def run(self, ct: Controller) -> None:
        if not self.initialized:
            self._init(ct)
            self.initialized = True

        self.placed_marker_this_turn = False
        rnd = ct.get_current_round()

        if not self.raiding:
            if self.builder_id in RAIDER_IDS and rnd >= RAIDER_START:
                self.raiding = True
                self.nav_state = {}
            elif self.builder_id >= NUM_BUILDERS:
                self.raiding = True
            elif self.turns_without_ore >= IDLE_BEFORE_RAID and self.has_income:
                self.raiding = True
                self.nav_state = {}

        if self.raiding:
            self._raid(ct)
        else:
            self._economy(ct)

    def _init(self, ct: Controller) -> None:
        pos = ct.get_position()
        for eid in ct.get_nearby_entities():
            if (
                ct.get_entity_type(eid) == EntityType.CORE
                and ct.get_team(eid) == ct.get_team()
            ):
                self.core_pos = ct.get_position(eid)
                break

        bid = ct.get_tile_building_id(pos)
        if (
            bid is not None
            and ct.get_entity_type(bid) == EntityType.MARKER
            and ct.get_team(bid) == ct.get_team()
        ):
            val = ct.get_marker_value(bid)
            if val & TAG_MASK == TAG_ASSIGN:
                sector = val & 0xFF
                self.builder_id = sector
                if sector < len(SECTOR_DIRS):
                    self.sector_dir = SECTOR_DIRS[sector]
                if sector >= NUM_BUILDERS:
                    self.raiding = True

        if self.sector_dir is None:
            self.sector_dir = random.choice(DIRS)

        if not self.raiding:
            self._new_explore_target(ct)

    def _place_marker(self, ct: Controller, val: int) -> None:
        if self.placed_marker_this_turn:
            return
        pos = ct.get_position()
        for d in Direction:
            tile = pos.add(d)
            if ct.can_place_marker(tile):
                ct.place_marker(tile, val)
                self.placed_marker_this_turn = True
                return

    def _new_explore_target(self, ct: Controller) -> None:
        if self.core_pos is None or self.sector_dir is None:
            return
        w = ct.get_map_width()
        h = ct.get_map_height()
        pos = ct.get_position()

        explored = scan_explored_blocks(ct)

        for _ in range(8):
            dx, dy = self.sector_dir.delta()
            dist = random.randint(8, max(w, h) // 2)
            tx = max(1, min(w - 2, pos.x + dx * dist + random.randint(-3, 3)))
            ty = max(1, min(h - 2, pos.y + dy * dist + random.randint(-3, 3)))
            bx, by = tx // BLOCK_SIZE, ty // BLOCK_SIZE
            if (bx, by) not in explored:
                self.explore_target = Position(tx, ty)
                self.explore_turns = 0
                self.nav_state = {}
                return

        self.sector_dir = random.choice(DIRS)
        dx, dy = self.sector_dir.delta()
        dist = random.randint(8, max(w, h) // 2)
        self.explore_target = Position(
            max(1, min(w - 2, pos.x + dx * dist)),
            max(1, min(h - 2, pos.y + dy * dist)),
        )
        self.explore_turns = 0
        self.nav_state = {}

    def _economy(self, ct: Controller) -> None:
        pos = ct.get_position()
        ti, _ax = ct.get_global_resources()

        if not self.has_income and ti > self.last_ti:
            self.has_income = True
        self.last_ti = ti

        skip = self.has_income

        ore = adjacent_ore(ct)
        if (
            ore is not None
            and (ore.x, ore.y) not in self.visited_ore
            and ct.can_build_harvester(ore)
        ):
            ct.build_harvester(ore)
            self.visited_ore.add((ore.x, ore.y))
            self.turns_without_ore = 0
            self._new_explore_target(ct)
            return

        visible_ore = nearest_ore(ct)
        if (
            visible_ore is not None
            and (visible_ore.x, visible_ore.y) not in self.visited_ore
            and self.core_pos is not None
        ):
            self.turns_without_ore = 0
            bugnav_conv(ct, visible_ore, self.core_pos, self.nav_state, skip_ore=skip)
            return

        self.turns_without_ore += 1

        if self.core_pos is None:
            return

        if self.turns_without_ore % 15 == 0:
            bx = pos.x // BLOCK_SIZE
            by = pos.y // BLOCK_SIZE
            self._place_marker(ct, mk_explored(bx, by))

        self.explore_turns += 1
        if self.explore_turns > 30 or (
            self.explore_target is not None
            and pos.distance_squared(self.explore_target) <= 4
        ):
            self.sector_dir = random.choice(DIRS)
            self._new_explore_target(ct)

        if self.explore_target is not None:
            if self.has_income:
                bugnav_road(ct, self.explore_target, self.nav_state)
            else:
                bugnav_conv(
                    ct,
                    self.explore_target,
                    self.core_pos,
                    self.nav_state,
                    skip_ore=skip,
                )

    def _raid(self, ct: Controller) -> None:
        if self.core_pos is None:
            return
        pos = ct.get_position()

        enemy = find_enemy_infra(ct)
        if enemy is not None:
            if pos.distance_squared(enemy) == 0:
                ct.self_destruct()
                return
            bugnav_road(ct, enemy, self.nav_state)
            return

        w = ct.get_map_width()
        h = ct.get_map_height()
        enemy_core = Position(w - 1 - self.core_pos.x, h - 1 - self.core_pos.y)

        if pos.distance_squared(enemy_core) <= 2:
            ct.self_destruct()
            return

        bugnav_road(ct, enemy_core, self.nav_state)


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
