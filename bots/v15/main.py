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

SPOKES = [
    Direction.NORTH, Direction.NORTHEAST, Direction.EAST, Direction.SOUTHEAST,
    Direction.SOUTH, Direction.SOUTHWEST, Direction.WEST, Direction.NORTHWEST,
]

# Phase thresholds (state-based, not turn-based)
MIN_HARVESTERS_FOR_DEFENSE = 2
MIN_INCOME_FOR_FOUNDRY = 15
MIN_INCOME_FOR_ATTACK = 10

# Builder allocation
NUM_INITIAL_BUILDERS = 8
MAX_BUILDERS = 50

# Marker ADT: 2-bit tag
TAG_ID = 0 << 30        # builder id assignment
TAG_THREAT = 1 << 30    # enemy spotted: x(6) y(6)
TAG_REPAIR = 2 << 30    # chain broken: x(6) y(6)
TAG_ROLE = 3 << 30      # builder role broadcast: bid(8) role(4) x(6) y(6)
TAG_MASK = 0xC000_0000

ROLE_EXPLORE = 0
ROLE_DEFEND = 1
ROLE_MAINTAIN = 2
ROLE_RAID = 3


def mk_id(bid: int) -> int:
    return TAG_ID | (bid & 0xFF)


def mk_threat(x: int, y: int) -> int:
    return TAG_THREAT | ((x & 0x3F) << 6) | (y & 0x3F)


def mk_repair(x: int, y: int) -> int:
    return TAG_REPAIR | ((x & 0x3F) << 6) | (y & 0x3F)


def mk_role(bid: int, role: int, x: int, y: int) -> int:
    return TAG_ROLE | ((bid & 0xFF) << 16) | ((role & 0xF) << 12) | ((x & 0x3F) << 6) | (y & 0x3F)


def decode_pos6(val: int) -> tuple[int, int]:
    return (val >> 6) & 0x3F, val & 0x3F


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
        if et in (EntityType.CONVEYOR, EntityType.HARVESTER, EntityType.ARMOURED_CONVEYOR,
                  EntityType.SPLITTER, EntityType.BRIDGE, EntityType.FOUNDRY):
            ep = ct.get_position(eid)
            d = pos.distance_squared(ep)
            if d < best_d:
                best_d = d
                best = ep
    return best


def find_enemy_builder(ct: Controller) -> Position | None:
    my = ct.get_team()
    pos = ct.get_position()
    best = None
    best_d = 999999
    for eid in ct.get_nearby_entities():
        if ct.get_team(eid) == my:
            continue
        if ct.get_entity_type(eid) == EntityType.BUILDER_BOT:
            ep = ct.get_position(eid)
            d = pos.distance_squared(ep)
            if d < best_d:
                best_d = d
                best = ep
    return best


def read_nearby_markers(ct: Controller) -> list[int]:
    vals = []
    my = ct.get_team()
    for tile in ct.get_nearby_tiles():
        bid = ct.get_tile_building_id(tile)
        if bid is None:
            continue
        if ct.get_entity_type(bid) != EntityType.MARKER:
            continue
        if ct.get_team(bid) != my:
            continue
        vals.append(ct.get_marker_value(bid))
    return vals


def find_broken_chain(ct: Controller) -> Position | None:
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
        out_env = ct.get_tile_env(out)
        if out_bid is None and out_env != Environment.WALL:
            core_near = False
            for eid in ct.get_nearby_entities():
                if ct.get_entity_type(eid) == EntityType.CORE and ct.get_team(eid) == my:
                    cp = ct.get_position(eid)
                    if abs(out.x - cp.x) <= 1 and abs(out.y - cp.y) <= 1:
                        core_near = True
            if not core_near:
                return out
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
        self.harvesters_seen = 0

    def run(self, ct: Controller) -> None:
        ti, ax = ct.get_global_resources()
        rnd = ct.get_current_round()
        cost = ct.get_builder_bot_cost()[0]
        core_pos = ct.get_position()

        my = ct.get_team()
        h_count = 0
        for eid in ct.get_nearby_entities():
            if ct.get_team(eid) == my and ct.get_entity_type(eid) == EntityType.HARVESTER:
                h_count += 1
        self.harvesters_seen = max(self.harvesters_seen, h_count)

        if self.spawned < NUM_INITIAL_BUILDERS:
            if ti < cost + ct.get_harvester_cost()[0]:
                return
        elif self.spawned >= MAX_BUILDERS or ti < 1500 or rnd % 20 != 0:
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
        self.nav = BugNav()
        self.role = ROLE_EXPLORE
        self.target: Position | None = None
        self.spoke_dir: Direction | None = None
        self.visited_ore: set[tuple[int, int]] = set()
        self.explore_t = 0
        self.no_ore_t = 0
        self.has_income = False
        self.last_ti = 0
        self.init_done = False
        self.harvesters_built = 0
        self.marker_cooldown = 0
        self.defense_built = False

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

        if self.bid >= NUM_INITIAL_BUILDERS:
            self.role = ROLE_RAID
        else:
            self._pick_target(ct)

        self.init_done = True

    def _pick_target(self, ct: Controller) -> None:
        if not self.core:
            return
        w, h = ct.get_map_width(), ct.get_map_height()
        pos = ct.get_position()

        my = ct.get_team()
        dir_density = {}
        for d in DIRS:
            count = 0
            for r in range(1, 5):
                dx, dy = d.delta()
                check = Position(pos.x + dx * r, pos.y + dy * r)
                if not in_bounds(ct, check) or not ct.is_in_vision(check):
                    continue
                bid = ct.get_tile_building_id(check)
                if bid is not None and ct.get_team(bid) == my:
                    et = ct.get_entity_type(bid)
                    if et in (EntityType.CONVEYOR, EntityType.ROAD):
                        count += 1
            dir_density[d] = count

        best = sorted(DIRS, key=lambda d: dir_density.get(d, 0))
        pick = best[random.randint(0, min(2, len(best) - 1))]

        dx, dy = pick.delta()
        dist = random.randint(8, max(w, h) // 2)
        tx = max(1, min(w - 2, pos.x + dx * dist + random.randint(-2, 2)))
        ty = max(1, min(h - 2, pos.y + dy * dist + random.randint(-2, 2)))
        self.target = Position(tx, ty)
        self.explore_t = 0
        self.nav.reset()

    def _place_marker(self, ct: Controller, val: int) -> None:
        if self.marker_cooldown > 0:
            return
        pos = ct.get_position()
        for d in Direction:
            t = pos.add(d)
            if ct.can_place_marker(t):
                ct.place_marker(t, val)
                self.marker_cooldown = 5
                return

    def _broadcast_role(self, ct: Controller) -> None:
        pos = ct.get_position()
        self._place_marker(ct, mk_role(self.bid, self.role, pos.x, pos.y))

    def _scan_threats(self, ct: Controller) -> Position | None:
        for val in read_nearby_markers(ct):
            if val & TAG_MASK == TAG_THREAT:
                x, y = decode_pos6(val)
                return Position(x, y)
        return None

    def _scan_repairs(self, ct: Controller) -> Position | None:
        for val in read_nearby_markers(ct):
            if val & TAG_MASK == TAG_REPAIR:
                x, y = decode_pos6(val)
                return Position(x, y)
        return None

    def _count_roles_nearby(self, ct: Controller) -> dict:
        counts = {ROLE_EXPLORE: 0, ROLE_DEFEND: 0, ROLE_MAINTAIN: 0, ROLE_RAID: 0}
        for val in read_nearby_markers(ct):
            if val & TAG_MASK == TAG_ROLE:
                role = (val >> 12) & 0xF
                if role in counts:
                    counts[role] += 1
        return counts

    def _decide_role(self, ct: Controller) -> None:
        if self.bid >= NUM_INITIAL_BUILDERS:
            self.role = ROLE_RAID
            return

        rnd = ct.get_current_round()
        ti, _ = ct.get_global_resources()

        enemy_near = find_enemy_builder(ct)
        if enemy_near and self.core:
            dist_to_core = enemy_near.distance_squared(self.core)
            if dist_to_core < 200 and not self.defense_built:
                self.role = ROLE_DEFEND
                return

        broken = find_broken_chain(ct)
        if broken and self.has_income:
            self._place_marker(ct, mk_repair(broken.x, broken.y))
            self.role = ROLE_MAINTAIN
            self.target = broken
            self.nav.reset()
            return

        if self.no_ore_t > 60 and self.has_income and rnd > 300:
            self.role = ROLE_RAID
            self.nav.reset()
            return

        self.role = ROLE_EXPLORE

    def run(self, ct: Controller) -> None:
        if not self.init_done:
            self._setup(ct)

        if self.marker_cooldown > 0:
            self.marker_cooldown -= 1

        pos = ct.get_position()
        ti, _ = ct.get_global_resources()
        rnd = ct.get_current_round()

        if not self.has_income and ti > self.last_ti:
            self.has_income = True
        self.last_ti = ti

        enemy_builder = find_enemy_builder(ct)
        if enemy_builder:
            self._place_marker(ct, mk_threat(enemy_builder.x, enemy_builder.y))

        if rnd % 10 == 0 and self.role != ROLE_RAID:
            self._decide_role(ct)

        if rnd % 20 == 0:
            self._broadcast_role(ct)

        if self.role == ROLE_EXPLORE:
            self._do_explore(ct)
        elif self.role == ROLE_DEFEND:
            self._do_defend(ct)
        elif self.role == ROLE_MAINTAIN:
            self._do_maintain(ct)
        elif self.role == ROLE_RAID:
            self._do_raid(ct)

    def _do_explore(self, ct: Controller) -> None:
        pos = ct.get_position()
        skip = self.has_income

        ore = adjacent_ore(ct)
        if ore and (ore.x, ore.y) not in self.visited_ore and ct.can_build_harvester(ore):
            ct.build_harvester(ore)
            self.visited_ore.add((ore.x, ore.y))
            self.harvesters_built += 1
            self.no_ore_t = 0
            self._pick_target(ct)
            return

        vis = nearest_ore(ct)
        if vis and (vis.x, vis.y) not in self.visited_ore and self.core:
            self.no_ore_t = 0
            self.nav.go(ct, vis, lambda d: step_conv(ct, d, self.core, skip))
            return

        self.no_ore_t += 1

        if not self.core:
            return

        self.explore_t += 1
        if self.explore_t > 30 or (self.target and pos.distance_squared(self.target) <= 4):
            self._pick_target(ct)

        if self.target:
            self.nav.go(ct, self.target, lambda d: step_conv(ct, d, self.core, skip))

    def _do_defend(self, ct: Controller) -> None:
        pos = ct.get_position()
        if not self.core or not self.enemy_core:
            self.role = ROLE_EXPLORE
            return

        threat = self._scan_threats(ct)
        enemy = find_enemy_builder(ct)

        target_pos = threat or enemy
        if target_pos and pos.distance_squared(target_pos) <= 2:
            facing = toward(pos, target_pos)
            for d in Direction:
                t = pos.add(d)
                if ct.can_build_gunner(t, facing):
                    ct.build_gunner(t, facing)
                    self.defense_built = True
                    self.role = ROLE_EXPLORE
                    self._pick_target(ct)
                    return

        midpoint = Position(
            (self.core.x + self.enemy_core.x) // 2,
            (self.core.y + self.enemy_core.y) // 2,
        )
        defense_line = Position(
            (self.core.x + midpoint.x) // 2,
            (self.core.y + midpoint.y) // 2,
        )

        if pos.distance_squared(defense_line) <= 8:
            enemy_dir = toward(pos, self.enemy_core)
            for d in Direction:
                t = pos.add(d)
                if ct.can_build_gunner(t, enemy_dir):
                    ct.build_gunner(t, enemy_dir)
                    self.defense_built = True
                    self.role = ROLE_EXPLORE
                    self._pick_target(ct)
                    return

        self.nav.go(ct, defense_line, lambda d: step_conv(ct, d, self.core, self.has_income))

    def _do_maintain(self, ct: Controller) -> None:
        pos = ct.get_position()

        broken = find_broken_chain(ct)
        if broken:
            if pos.distance_squared(broken) <= GameConstants.ACTION_RADIUS_SQ:
                for d in Direction:
                    if ct.can_build_conveyor(broken, d):
                        ct.build_conveyor(broken, d)
                        self.role = ROLE_EXPLORE
                        self._pick_target(ct)
                        return
            if self.core:
                self.nav.go(ct, broken, lambda d: step_conv(ct, d, self.core, self.has_income))
            return

        repair = self._scan_repairs(ct)
        if repair:
            if self.core:
                self.nav.go(ct, repair, lambda d: step_conv(ct, d, self.core, self.has_income))
            return

        self.role = ROLE_EXPLORE
        self._pick_target(ct)

    def _do_raid(self, ct: Controller) -> None:
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


# --- Turret ---


class TurretUnit:
    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.GUNNER:
            try:
                target = ct.get_gunner_target()
                if target and ct.can_fire(target):
                    ct.fire(target)
            except Exception:
                pass


# --- Player ---


class Player:
    def __init__(self) -> None:
        self.core_bot = CoreBot()
        self.builder = BuilderUnit()
        self.turret = TurretUnit()

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            self.core_bot.run(ct)
        elif etype == EntityType.BUILDER_BOT:
            self.builder.run(ct)
        elif etype in (EntityType.GUNNER, EntityType.SENTINEL, EntityType.BREACH):
            self.turret.run(ct)
