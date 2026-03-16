import random

from cambc import Controller, Direction, EntityType, Environment, Position

DIRS = [d for d in Direction if d != Direction.CENTRE]

SPOKES = [
    Direction.NORTH, Direction.NORTHEAST, Direction.EAST, Direction.SOUTHEAST,
    Direction.SOUTH, Direction.SOUTHWEST, Direction.WEST, Direction.NORTHWEST,
]

NUM_BUILDERS = 8

TAG_ID = 0 << 30
TAG_MASK = 0xC000_0000


def mk_id(bid: int) -> int:
    return TAG_ID | (bid & 0xFF)


def toward(a: Position, b: Position) -> Direction:
    return a.direction_to(b)


def in_bounds(ct: Controller, p: Position) -> bool:
    return 0 <= p.x < ct.get_map_width() and 0 <= p.y < ct.get_map_height()


def is_wall(ct: Controller, p: Position) -> bool:
    return not in_bounds(ct, p) or ct.get_tile_env(p) == Environment.WALL


def is_ore(ct: Controller, p: Position) -> bool:
    return in_bounds(ct, p) and ct.get_tile_env(p) in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE)


def adjacent_ore(ct: Controller) -> Position | None:
    pos = ct.get_position()
    for d in Direction:
        t = pos.add(d)
        if in_bounds(ct, t) and is_ore(ct, t) and ct.get_tile_building_id(t) is None:
            return t
    return None


def nearest_ore(ct: Controller) -> Position | None:
    best = None
    best_d = 999999
    pos = ct.get_position()
    for t in ct.get_nearby_tiles():
        if not is_ore(ct, t) or ct.get_tile_building_id(t) is not None:
            continue
        d = pos.distance_squared(t)
        if d < best_d:
            best_d = d
            best = t
    return best


def find_enemy_infra(ct: Controller) -> Position | None:
    my = ct.get_team()
    pos = ct.get_position()
    best = None
    best_d = 999999
    for eid in ct.get_nearby_entities():
        if ct.get_team(eid) == my:
            continue
        et = ct.get_entity_type(eid)
        if et in (EntityType.CONVEYOR, EntityType.HARVESTER, EntityType.ARMOURED_CONVEYOR):
            ep = ct.get_position(eid)
            d = pos.distance_squared(ep)
            if d < best_d:
                best_d = d
                best = ep
    return best


def find_broken_conveyor(ct: Controller) -> Position | None:
    my = ct.get_team()
    for tile in ct.get_nearby_tiles():
        bid = ct.get_tile_building_id(tile)
        if bid is None:
            continue
        if ct.get_entity_type(bid) != EntityType.CONVEYOR:
            continue
        if ct.get_team(bid) != my:
            continue
        d = ct.get_direction(bid)
        dx, dy = d.delta()
        out = Position(tile.x + dx, tile.y + dy)
        if not in_bounds(ct, out) or not ct.is_in_vision(out):
            continue
        out_bid = ct.get_tile_building_id(out)
        if out_bid is None:
            return tile
    return None


def find_dead_end_conveyor(ct: Controller) -> Position | None:
    my = ct.get_team()
    pos = ct.get_position()

    has_input = set()
    conveyors = {}
    for tile in ct.get_nearby_tiles():
        bid = ct.get_tile_building_id(tile)
        if bid is None:
            continue
        if ct.get_entity_type(bid) != EntityType.CONVEYOR:
            continue
        if ct.get_team(bid) != my:
            continue
        d = ct.get_direction(bid)
        dx, dy = d.delta()
        out = Position(tile.x + dx, tile.y + dy)
        conveyors[(tile.x, tile.y)] = out
        has_input.add((out.x, out.y))

    for (cx, cy), out in conveyors.items():
        if (cx, cy) not in has_input:
            if ct.get_tile_building_id(Position(cx, cy)) is not None:
                return Position(cx, cy)
    return None


class BugNav:
    def __init__(self) -> None:
        self.lp = None
        self.stuck = 0
        self.wf = False
        self.ws = 1
        self.cl = 999999

    def reset(self) -> None:
        self.__init__()

    def go(self, ct: Controller, target: Position, step_fn) -> bool:
        pos = ct.get_position()
        d = toward(pos, target)
        dist = pos.distance_squared(target)

        if self.lp == (pos.x, pos.y):
            self.stuck += 1
        else:
            self.stuck = 0
        self.lp = (pos.x, pos.y)

        if self.stuck > 10:
            self.wf = False
            self.ws = -self.ws
            self.stuck = 0

        if not self.wf:
            if step_fn(d):
                self.cl = min(self.cl, dist)
                return True
            self.wf = True
            self.cl = dist

        scan = d
        for _ in range(8):
            if step_fn(scan):
                nd = ct.get_position().distance_squared(target)
                if nd < self.cl:
                    self.wf = False
                    self.cl = nd
                return True
            scan = scan.rotate_right() if self.ws == 1 else scan.rotate_left()
        return False


def step_conv(ct: Controller, d: Direction, core: Position, skip_ore: bool) -> bool:
    nxt = ct.get_position().add(d)
    if is_wall(ct, nxt):
        return False
    if not skip_ore or not is_ore(ct, nxt):
        if ct.can_build_conveyor(nxt, d.opposite()):
            ct.build_conveyor(nxt, d.opposite())
    if ct.can_move(d):
        ct.move(d)
        return True
    return False


def step_road(ct: Controller, d: Direction) -> bool:
    nxt = ct.get_position().add(d)
    if is_wall(ct, nxt):
        return False
    if ct.can_build_road(nxt):
        ct.build_road(nxt)
    if ct.can_move(d):
        ct.move(d)
        return True
    return False


# --- Core ---


class CoreBot:
    def __init__(self) -> None:
        self.spawned = 0

    def run(self, ct: Controller) -> None:
        ti, _ = ct.get_global_resources()
        cost = ct.get_builder_bot_cost()[0]
        rnd = ct.get_current_round()
        core_pos = ct.get_position()

        if self.spawned < NUM_BUILDERS:
            if ti < cost + ct.get_harvester_cost()[0]:
                return
        elif self.spawned >= 50 or ti < 1500 or rnd % 20 != 0:
            return

        spoke = self.spawned % len(SPOKES)
        sd = SPOKES[spoke]
        for d in [sd, sd.rotate_left(), sd.rotate_right()] + DIRS:
            sp = core_pos.add(d)
            if ct.can_spawn(sp):
                ct.spawn_builder(sp)
                if ct.can_place_marker(sp):
                    ct.place_marker(sp, mk_id(self.spawned))
                self.spawned += 1
                return


# --- Builder ---


class BuilderUnit:
    def __init__(self) -> None:
        self.core: Position | None = None
        self.enemy_core: Position | None = None
        self.bid = 0
        self.spoke_dir: Direction | None = None
        self.nav = BugNav()
        self.role = "explore"
        self.target: Position | None = None
        self.visited: set[tuple[int, int]] = set()
        self.explore_t = 0
        self.has_income = False
        self.last_ti = 0
        self.no_ore_t = 0
        self.init_done = False

    def _setup(self, ct: Controller) -> None:
        pos = ct.get_position()
        for eid in ct.get_nearby_entities():
            if ct.get_entity_type(eid) == EntityType.CORE and ct.get_team(eid) == ct.get_team():
                self.core = ct.get_position(eid)
                break

        bid = ct.get_tile_building_id(pos)
        if bid is not None and ct.get_entity_type(bid) == EntityType.MARKER and ct.get_team(bid) == ct.get_team():
            val = ct.get_marker_value(bid)
            if val & TAG_MASK == TAG_ID:
                self.bid = val & 0xFF

        if self.bid < len(SPOKES):
            self.spoke_dir = SPOKES[self.bid]
        else:
            self.spoke_dir = random.choice(DIRS)

        if self.core:
            w, h = ct.get_map_width(), ct.get_map_height()
            self.enemy_core = Position(w - 1 - self.core.x, h - 1 - self.core.y)

        if self.bid >= NUM_BUILDERS:
            self.role = "raid"
        else:
            self._pick_explore_target(ct)

        self.init_done = True

    def _pick_explore_target(self, ct: Controller) -> None:
        if not self.core or not self.spoke_dir:
            return
        w, h = ct.get_map_width(), ct.get_map_height()
        pos = ct.get_position()
        dx, dy = self.spoke_dir.delta()
        dist = random.randint(8, max(w, h) // 2)
        tx = max(1, min(w - 2, pos.x + dx * dist + random.randint(-3, 3)))
        ty = max(1, min(h - 2, pos.y + dy * dist + random.randint(-3, 3)))
        self.target = Position(tx, ty)
        self.explore_t = 0
        self.nav.reset()

    def run(self, ct: Controller) -> None:
        if not self.init_done:
            self._setup(ct)

        ti, _ = ct.get_global_resources()
        if not self.has_income and ti > self.last_ti:
            self.has_income = True
        self.last_ti = ti

        if self.role == "explore":
            self._run_explore(ct)
            self._check_transition(ct)
        elif self.role == "maintain":
            self._run_maintain(ct)
        elif self.role == "raid":
            self._run_raid(ct)

    def _check_transition(self, ct: Controller) -> None:
        rnd = ct.get_current_round()
        if not self.has_income:
            return

        if self.no_ore_t > 60:
            broken = find_broken_conveyor(ct)
            if broken is not None:
                self.role = "maintain"
                self.target = broken
                self.nav.reset()
                return

            dead = find_dead_end_conveyor(ct)
            if dead is not None:
                self.role = "maintain"
                self.target = dead
                self.nav.reset()
                return

            if rnd > 300:
                self.role = "raid"
                self.nav.reset()

    def _run_explore(self, ct: Controller) -> None:
        pos = ct.get_position()
        skip = self.has_income

        ore = adjacent_ore(ct)
        if ore and (ore.x, ore.y) not in self.visited and ct.can_build_harvester(ore):
            ct.build_harvester(ore)
            self.visited.add((ore.x, ore.y))
            self.no_ore_t = 0
            self._pick_explore_target(ct)
            return

        vis = nearest_ore(ct)
        if vis and (vis.x, vis.y) not in self.visited and self.core:
            self.no_ore_t = 0
            self.nav.go(ct, vis, lambda d: step_conv(ct, d, self.core, skip))
            return

        self.no_ore_t += 1

        if not self.core:
            return

        self.explore_t += 1
        if self.explore_t > 30 or (self.target and pos.distance_squared(self.target) <= 4):
            base = SPOKES[self.bid % len(SPOKES)]
            self.spoke_dir = random.choice([base, base.rotate_left(), base.rotate_right()])
            self._pick_explore_target(ct)

        if self.target:
            self.nav.go(ct, self.target, lambda d: step_conv(ct, d, self.core, skip))

    def _run_maintain(self, ct: Controller) -> None:
        pos = ct.get_position()

        broken = find_broken_conveyor(ct)
        if broken:
            bid = ct.get_tile_building_id(broken)
            if bid is not None:
                d = ct.get_direction(bid)
                dx, dy = d.delta()
                out = Position(broken.x + dx, broken.y + dy)
                if pos.distance_squared(out) <= 2:
                    if ct.can_build_conveyor(out, d):
                        ct.build_conveyor(out, d)
                        self.role = "explore"
                        self._pick_explore_target(ct)
                        return
                self.nav.go(ct, out, lambda d: step_road(ct, d))
                return

        dead = find_dead_end_conveyor(ct)
        if dead:
            if pos.distance_squared(dead) <= 2 and ct.can_destroy(dead):
                ct.destroy(dead)
                return
            self.nav.go(ct, dead, lambda d: step_road(ct, d))
            return

        self.role = "explore"
        self._pick_explore_target(ct)

    def _run_raid(self, ct: Controller) -> None:
        pos = ct.get_position()

        enemy = find_enemy_infra(ct)
        if enemy:
            if pos.distance_squared(enemy) == 0:
                ct.self_destruct()
                return
            self.nav.go(ct, enemy, lambda d: step_road(ct, d))
            return

        if self.enemy_core:
            if pos.distance_squared(self.enemy_core) <= 2:
                ct.self_destruct()
                return
            self.nav.go(ct, self.enemy_core, lambda d: step_road(ct, d))


# --- Player ---


class Player:
    def __init__(self) -> None:
        self.core_bot = CoreBot()
        self.builder = BuilderUnit()

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            self.core_bot.run(ct)
        elif etype == EntityType.BUILDER_BOT:
            self.builder.run(ct)
