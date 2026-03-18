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
RAIDER_START = 150
IDLE_BEFORE_RAID = 40
HUNT_TIMEOUT = 10

MARKER_ASSIGN = 0xA000_0000
MARKER_TYPE_MASK = 0xF000_0000

TRANSPORT = frozenset(
    {
        EntityType.CONVEYOR,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.SPLITTER,
        EntityType.BRIDGE,
    },
)

INFRA = TRANSPORT | {EntityType.HARVESTER, EntityType.FOUNDRY}


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


def in_degree(ct: Controller, pos: Position, my_team) -> int:
    count = 0
    for eid in ct.get_nearby_entities():
        if ct.get_team(eid) == my_team:
            continue
        et = ct.get_entity_type(eid)
        if et not in TRANSPORT or et == EntityType.BRIDGE:
            continue
        ep = ct.get_position(eid)
        if ep.x == pos.x and ep.y == pos.y:
            continue
        ed = ct.get_direction(eid)
        dx, dy = ed.delta()
        if ep.x + dx == pos.x and ep.y + dy == pos.y:
            count += 1
    return count


def bugnav_step(
    ct: Controller,
    target: Position,
    core_pos: Position | None,
    state: dict,
    *,
    skip_ore: bool = False,
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
        if _try_step(ct, d, core_pos, skip_ore):
            state["closest"] = min(state.get("closest", 999999), dist)
            return True
        state["wall_following"] = True
        state.setdefault("wall_side", 1)
        state["closest"] = dist

    scan = d
    side = state.get("wall_side", 1)
    for _ in range(8):
        if _try_step(ct, scan, core_pos, skip_ore):
            new_dist = ct.get_position().distance_squared(target)
            if new_dist < state.get("closest", 999999):
                state["wall_following"] = False
                state["closest"] = new_dist
            return True
        scan = scan.rotate_right() if side == 1 else scan.rotate_left()

    return False


def _try_step(
    ct: Controller,
    d: Direction,
    core_pos: Position | None,
    skip_ore: bool = False,
) -> bool:
    pos = ct.get_position()
    next_pos = pos.add(d)
    if is_wall(ct, next_pos):
        return False
    if core_pos is not None:
        if not skip_ore or not is_ore(ct, next_pos):
            conv_dir = d.opposite()
            if ct.can_build_conveyor(next_pos, conv_dir):
                ct.build_conveyor(next_pos, conv_dir)
    elif ct.can_build_road(next_pos):
        ct.build_road(next_pos)
    if ct.can_move(d):
        ct.move(d)
        return True
    return False


def _try_step_walk(ct: Controller, d: Direction) -> bool:
    next_pos = ct.get_position().add(d)
    if is_wall(ct, next_pos):
        return False
    if ct.can_move(d):
        ct.move(d)
        return True
    return False


class CoreBot:
    def __init__(self) -> None:
        self.num_spawned = 0

    def run(self, ct: Controller) -> None:
        core_pos = ct.get_position()
        ti, _ax = ct.get_global_resources()
        bot_cost = ct.get_builder_bot_cost()[0]
        rnd = ct.get_current_round()
        my = ct.get_team()

        for eid in ct.get_nearby_entities():
            if (
                ct.get_team(eid) != my
                and ct.get_entity_type(eid) == EntityType.BUILDER_BOT
                and core_pos.distance_squared(ct.get_position(eid)) <= 36
            ):
                if ti >= bot_cost:
                    for d in DIRS:
                        sp = core_pos.add(d)
                        if ct.can_spawn(sp):
                            ct.spawn_builder(sp)
                            self.num_spawned += 1
                            return
                return

        if self.num_spawned < NUM_BUILDERS:
            if ti < bot_cost + ct.get_harvester_cost()[0]:
                return
        elif rnd < RAIDER_START or ti < 300:
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


class BuilderBot:
    def __init__(self) -> None:
        self.core_pos: Position | None = None
        self.enemy_core: Position | None = None
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
        self.hunt_turns = 0

    def run(self, ct: Controller) -> None:
        if not self.initialized:
            self._init(ct)
            self.initialized = True

        rnd = ct.get_current_round()

        if not self.raiding:
            should_raid = False
            if (self.builder_id in RAIDER_IDS and rnd >= RAIDER_START) or (
                self.turns_without_ore >= IDLE_BEFORE_RAID and self.has_income
            ):
                should_raid = True
            if self.builder_id >= NUM_BUILDERS:
                should_raid = True
            if should_raid:
                self.raiding = True
                self.nav_state = {}
                self.hunt_turns = 0

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
            if val & MARKER_TYPE_MASK == MARKER_ASSIGN:
                sector = val & 0xFF
                self.builder_id = sector
                if sector < len(SECTOR_DIRS):
                    self.sector_dir = SECTOR_DIRS[sector]
                if sector >= NUM_BUILDERS:
                    self.raiding = True

        if self.sector_dir is None:
            self.sector_dir = random.choice(DIRS)

        if self.core_pos:
            w, h = ct.get_map_width(), ct.get_map_height()
            self.enemy_core = Position(w - 1 - self.core_pos.x, h - 1 - self.core_pos.y)

        if not self.raiding:
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
            bugnav_step(ct, visible_ore, self.core_pos, self.nav_state, skip_ore=skip)
            return

        self.turns_without_ore += 1

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
            bugnav_step(
                ct,
                self.explore_target,
                self.core_pos,
                self.nav_state,
                skip_ore=skip,
            )

    def _find_active_target(self, ct: Controller, my_team) -> Position | None:
        best = None
        best_core_dist = 999999
        for eid in ct.get_nearby_entities():
            if ct.get_team(eid) == my_team:
                continue
            et = ct.get_entity_type(eid)
            if et in (EntityType.HARVESTER, EntityType.FOUNDRY):
                return ct.get_position(eid)
            if et not in TRANSPORT:
                continue
            if ct.get_stored_resource(eid) is None:
                continue
            ep = ct.get_position(eid)
            cd = ep.distance_squared(self.enemy_core)
            if cd < best_core_dist:
                best_core_dist = cd
                best = ep
        return best

    def _find_any_infra(self, ct: Controller, my_team) -> Position | None:
        best = None
        best_core_dist = 999999
        for eid in ct.get_nearby_entities():
            if ct.get_team(eid) == my_team:
                continue
            et = ct.get_entity_type(eid)
            if et not in INFRA:
                continue
            ep = ct.get_position(eid)
            cd = ep.distance_squared(self.enemy_core)
            if cd < best_core_dist:
                best_core_dist = cd
                best = ep
        return best

    def _raid(self, ct: Controller) -> None:
        if self.core_pos is None or self.enemy_core is None:
            return
        pos = ct.get_position()
        my = ct.get_team()

        bid = ct.get_tile_building_id(pos)
        on_enemy_infra = (
            bid is not None
            and ct.get_team(bid) != my
            and ct.get_entity_type(bid) in INFRA
        )

        if on_enemy_infra:
            on_type = ct.get_entity_type(bid)
            self.hunt_turns += 1

            if on_type in (EntityType.HARVESTER, EntityType.FOUNDRY):
                ct.self_destruct()
                return

            active = on_type in TRANSPORT and ct.get_stored_resource(bid) is not None

            if active and in_degree(ct, pos, my) >= 2:
                ct.self_destruct()
                return

            if active and pos.distance_squared(self.enemy_core) <= 20:
                ct.self_destruct()
                return

            if self.hunt_turns >= HUNT_TIMEOUT:
                if active:
                    ct.self_destruct()
                    return
                better = self._find_active_target(ct, my)
                if better:
                    self.hunt_turns = 0
                    self.nav_state = {}
                    bugnav_step(ct, better, None, self.nav_state)
                    return
                ct.self_destruct()
                return

            walk_state = {}
            bugnav_walk(ct, self.enemy_core, walk_state)
            return

        self.hunt_turns = 0

        active = self._find_active_target(ct, my)
        if active:
            bugnav_step(ct, active, None, self.nav_state)
            return

        any_infra = self._find_any_infra(ct, my)
        if any_infra:
            bugnav_step(ct, any_infra, None, self.nav_state)
            return

        bugnav_step(ct, self.enemy_core, None, self.nav_state)


def bugnav_walk(ct: Controller, target: Position, state: dict) -> bool:
    pos = ct.get_position()
    d = toward(pos, target)
    dist = pos.distance_squared(target)

    if state.get("last_pos") == (pos.x, pos.y):
        state["stuck"] = state.get("stuck", 0) + 1
    else:
        state["stuck"] = 0
    state["last_pos"] = (pos.x, pos.y)

    if state.get("stuck", 0) > 5:
        state["wall_following"] = False
        state["wall_side"] = -state.get("wall_side", 1)
        state["stuck"] = 0

    if not state.get("wall_following"):
        if _try_step_walk(ct, d):
            state["closest"] = min(state.get("closest", 999999), dist)
            return True
        state["wall_following"] = True
        state.setdefault("wall_side", 1)
        state["closest"] = dist

    scan = d
    side = state.get("wall_side", 1)
    for _ in range(8):
        if _try_step_walk(ct, scan):
            new_dist = ct.get_position().distance_squared(target)
            if new_dist < state.get("closest", 999999):
                state["wall_following"] = False
                state["closest"] = new_dist
            return True
        scan = scan.rotate_right() if side == 1 else scan.rotate_left()

    return False


class Player:
    def __init__(self) -> None:
        self.core = CoreBot()
        self.builder = BuilderBot()

    def run(self, ct: Controller) -> None:
        if ct.get_current_round() > 500:
            return
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            self.core.run(ct)
        elif etype == EntityType.BUILDER_BOT:
            self.builder.run(ct)
