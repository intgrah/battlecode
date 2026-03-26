import random

from cambc import (
    Controller,
    Direction,
    EntityType,
    Environment,
    GameConstants,
    Position,
)

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

NUM_BUILDERS = 3
ATTACK_ROUND = 800

MARKER_ASSIGN = 0xA000_0000
MARKER_ASSIGN_MASK = 0xF000_0000


def toward(pos: Position, target: Position) -> Direction:
    return pos.direction_to(target)


def in_bounds(ct: Controller, pos: Position) -> bool:
    return 0 <= pos.x < ct.get_map_width() and 0 <= pos.y < ct.get_map_height()


def is_wall(ct: Controller, pos: Position) -> bool:
    if not in_bounds(ct, pos):
        return True
    return ct.get_tile_env(pos) == Environment.WALL


def adjacent_ore(ct: Controller) -> Position | None:
    pos = ct.get_position()
    for d in Direction:
        tile = pos.add(d)
        if not in_bounds(ct, tile):
            continue
        if (
            ct.get_tile_env(tile)
            in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE)
            and ct.get_tile_building_id(tile) is None
        ):
            return tile
    return None


def nearest_ore(ct: Controller) -> Position | None:
    best = None
    best_dist = 999999
    pos = ct.get_position()
    for tile in ct.get_nearby_tiles():
        if ct.get_tile_env(tile) not in (
            Environment.ORE_TITANIUM,
            Environment.ORE_AXIONITE,
        ):
            continue
        if ct.get_tile_building_id(tile) is not None:
            continue
        d = pos.distance_squared(tile)
        if d < best_dist:
            best_dist = d
            best = tile
    return best


def bugnav_step(
    ct: Controller,
    target: Position,
    core_pos: Position | None,
    state: dict,
) -> bool:
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
        if _try_step(ct, d, core_pos):
            state["closest"] = min(state.get("closest", 999999), dist)
            return True
        state["wall_following"] = True
        state.setdefault("wall_side", 1)
        state["closest"] = dist

    scan = d
    side = state.get("wall_side", 1)
    for _ in range(8):
        if _try_step(ct, scan, core_pos):
            new_dist = ct.get_position().distance_squared(target)
            if new_dist < state.get("closest", 999999):
                state["wall_following"] = False
                state["closest"] = new_dist
            return True
        scan = scan.rotate_right() if side == 1 else scan.rotate_left()

    return False


def _try_step(ct: Controller, d: Direction, core_pos: Position | None) -> bool:
    pos = ct.get_position()
    next_pos = pos.add(d)
    if is_wall(ct, next_pos):
        return False
    if core_pos is not None:
        env = (
            ct.get_tile_env(next_pos) if in_bounds(ct, next_pos) else Environment.EMPTY
        )
        if env not in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE):
            conv_dir = d.opposite()
            if ct.can_build_conveyor(next_pos, conv_dir):
                ct.build_conveyor(next_pos, conv_dir)
    elif ct.can_build_road(next_pos):
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

        if self.num_spawned >= NUM_BUILDERS:
            return
        if ti < bot_cost + ct.get_harvester_cost()[0]:
            return

        sector = self.num_spawned

        for d in DIRS:
            spawn_pos = core_pos.add(d)
            if ct.can_spawn(spawn_pos):
                ct.spawn_builder(spawn_pos)
                if ct.can_place_marker(spawn_pos):
                    ct.place_marker(spawn_pos, MARKER_ASSIGN | sector)
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

    def run(self, ct: Controller) -> None:
        if not self.initialized:
            self._init(ct)
            self.initialized = True

        rnd = ct.get_current_round()
        if rnd >= ATTACK_ROUND:
            self._attack(ct)
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
            if val & MARKER_ASSIGN_MASK == MARKER_ASSIGN:
                sector = val & 0xFF
                if sector < len(SECTOR_DIRS):
                    self.sector_dir = SECTOR_DIRS[sector]

        if self.sector_dir is None:
            self.sector_dir = random.choice(DIRS)

        self._new_explore_target(ct)

    def _new_explore_target(self, ct: Controller) -> None:
        if self.core_pos is None or self.sector_dir is None:
            return
        w = ct.get_map_width()
        h = ct.get_map_height()
        pos = ct.get_position()

        dx, dy = self.sector_dir.delta()
        dist = random.randint(8, max(w, h) // 2)
        tx = pos.x + dx * dist + random.randint(-3, 3)
        ty = pos.y + dy * dist + random.randint(-3, 3)
        self.explore_target = Position(max(1, min(w - 2, tx)), max(1, min(h - 2, ty)))
        self.explore_turns = 0
        self.nav_state = {}

    def _economy(self, ct: Controller) -> None:
        pos = ct.get_position()

        ore = adjacent_ore(ct)
        if ore is not None and ct.can_build_harvester(ore):
            ct.build_harvester(ore)
            self._new_explore_target(ct)
            return

        visible_ore = nearest_ore(ct)
        if visible_ore is not None and self.core_pos is not None:
            bugnav_step(ct, visible_ore, self.core_pos, self.nav_state)
            return

        if self.core_pos is None:
            return

        self.explore_turns += 1
        if self.explore_turns > 40 or (
            self.explore_target is not None
            and pos.distance_squared(self.explore_target) <= 4
        ):
            self.sector_dir = random.choice(DIRS)
            self._new_explore_target(ct)

        if self.explore_target is not None:
            bugnav_step(ct, self.explore_target, self.core_pos, self.nav_state)

    def _attack(self, ct: Controller) -> None:
        if self.core_pos is None:
            return
        w = ct.get_map_width()
        h = ct.get_map_height()
        target = Position(w - 1 - self.core_pos.x, h - 1 - self.core_pos.y)
        pos = ct.get_position()

        if pos.distance_squared(target) <= GameConstants.ACTION_RADIUS_SQ:
            ct.self_destruct()
            return

        bugnav_step(ct, target, None, self.nav_state)


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
