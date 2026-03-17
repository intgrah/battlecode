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

NUM_INITIAL = 8
RAID_START = 150
IDLE_BEFORE_RAID = 50
MAX_GUNNERS_PER_BUILDER = 1

SPOKES = [
    Direction.NORTH,
    Direction.NORTHEAST,
    Direction.EAST,
    Direction.SOUTHEAST,
    Direction.SOUTH,
    Direction.SOUTHWEST,
    Direction.WEST,
    Direction.NORTHWEST,
]

TAG_ID = 0 << 30
TAG_MASK = 0xC000_0000


def mk_id(n: int) -> int:
    return TAG_ID | (n & 0xFF)


def toward(a: Position, b: Position) -> Direction:
    return a.direction_to(b)


def ib(ct: Controller, p: Position) -> bool:
    return 0 <= p.x < ct.get_map_width() and 0 <= p.y < ct.get_map_height()


def wall(ct: Controller, p: Position) -> bool:
    return not ib(ct, p) or ct.get_tile_env(p) == Environment.WALL


def ore_env(ct: Controller, p: Position) -> bool:
    return ib(ct, p) and ct.get_tile_env(p) in (
        Environment.ORE_TITANIUM,
        Environment.ORE_AXIONITE,
    )


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


def step_conv(ct: Controller, d: Direction) -> bool:
    pos = ct.get_position()
    nxt = pos.add(d)
    if wall(ct, nxt):
        return False
    if not ore_env(ct, nxt) and ct.can_build_conveyor(nxt, d.opposite()):
        ct.build_conveyor(nxt, d.opposite())
    if ct.can_move(d):
        ct.move(d)
        return True
    return False


def step_raid(ct: Controller, d: Direction) -> bool:
    nxt = ct.get_position().add(d)
    if wall(ct, nxt):
        return False
    if ct.can_move(d):
        ct.move(d)
        return True
    if ct.can_build_road(nxt):
        ct.build_road(nxt)
    if ct.can_move(d):
        ct.move(d)
        return True
    return False


class CoreBot:
    def __init__(self) -> None:
        self.spawned = 0

    def run(self, ct: Controller) -> None:
        ti, _ = ct.get_global_resources()
        cost = ct.get_builder_bot_cost()[0]
        rnd = ct.get_current_round()
        core_pos = ct.get_position()

        if self.spawned < NUM_INITIAL:
            if ti < cost + ct.get_harvester_cost()[0]:
                return
        elif rnd < RAID_START or ti < 400:
            return

        spoke = self.spawned % len(SPOKES)
        sd = SPOKES[spoke]
        for d in [sd, sd.rotate_left(), sd.rotate_right(), *DIRS]:
            sp = core_pos.add(d)
            if ct.can_spawn(sp):
                ct.spawn_builder(sp)
                if ct.can_place_marker(sp):
                    ct.place_marker(sp, mk_id(self.spawned))
                self.spawned += 1
                return


class BuilderAgent:
    def __init__(self) -> None:
        self.core: Position | None = None
        self.enemy_core: Position | None = None
        self.nav = BugNav()
        self.target: Position | None = None
        self.init_done = False
        self.spoke_dir: Direction | None = None
        self.idle_turns = 0
        self.has_income = False
        self.last_ti = 0
        self.builder_id = 0
        self.raiding = False
        self.visited_ore: set[tuple[int, int]] = set()
        self.explore_turns = 0
        self.harvesters_built = 0
        self.gunners_built = 0

    def _setup(self, ct: Controller) -> None:
        pos = ct.get_position()
        for eid in ct.get_nearby_entities():
            if (
                ct.get_entity_type(eid) == EntityType.CORE
                and ct.get_team(eid) == ct.get_team()
            ):
                self.core = ct.get_position(eid)
                break

        bid = ct.get_tile_building_id(pos)
        if (
            bid is not None
            and ct.get_entity_type(bid) == EntityType.MARKER
            and ct.get_team(bid) == ct.get_team()
        ):
            val = ct.get_marker_value(bid)
            if val & TAG_MASK == TAG_ID:
                sid = val & 0xFF
                self.builder_id = sid
                if sid < len(SPOKES):
                    self.spoke_dir = SPOKES[sid]
                if sid >= NUM_INITIAL:
                    self.raiding = True

        if self.spoke_dir is None:
            self.spoke_dir = random.choice(DIRS)

        if self.core:
            w, h = ct.get_map_width(), ct.get_map_height()
            self.enemy_core = Position(w - 1 - self.core.x, h - 1 - self.core.y)

        self.init_done = True

    def run(self, ct: Controller) -> None:
        if not self.init_done:
            self._setup(ct)

        if not self.core:
            return

        ti, _ = ct.get_global_resources()
        if not self.has_income and ti > self.last_ti:
            self.has_income = True
        self.last_ti = ti

        if not self.raiding:
            if self.idle_turns >= IDLE_BEFORE_RAID and self.has_income:
                self.raiding = True
                self.nav.reset()

        if self.raiding:
            self._raid(ct)
        else:
            self._economy(ct, ti)

    def _economy(self, ct: Controller, ti: int) -> None:
        pos = ct.get_position()
        my = ct.get_team()

        bid = ct.get_tile_building_id(pos)
        if bid is not None and ct.get_team(bid) != my:
            et = ct.get_entity_type(bid)
            if et in (
                EntityType.CONVEYOR,
                EntityType.ARMOURED_CONVEYOR,
                EntityType.SPLITTER,
                EntityType.HARVESTER,
                EntityType.FOUNDRY,
                EntityType.BRIDGE,
            ):
                ct.self_destruct()
                return

        for d in Direction:
            t = pos.add(d)
            if not ib(ct, t):
                continue
            if (
                ore_env(ct, t)
                and ct.get_tile_building_id(t) is None
                and (t.x, t.y) not in self.visited_ore
            ):
                if ct.can_build_harvester(t):
                    ct.build_harvester(t)
                    self.visited_ore.add((t.x, t.y))
                    self.idle_turns = 0
                    self.harvesters_built += 1
                    self._new_explore_target(ct)
                return

        rnd = ct.get_current_round()
        if (
            self.gunners_built < MAX_GUNNERS_PER_BUILDER
            and self.builder_id == 0
            and self.has_income
            and ti > 500
            and rnd > 200
            and self.harvesters_built >= 1
            and self.core
            and self.enemy_core
        ) and self._try_build_gunner(ct, pos):
            return

        best_ore = None
        best_d = 999999
        for t in ct.get_nearby_tiles():
            if (
                ore_env(ct, t)
                and ct.get_tile_building_id(t) is None
                and (t.x, t.y) not in self.visited_ore
            ):
                d = pos.distance_squared(t)
                if d < best_d:
                    best_d = d
                    best_ore = t

        if best_ore:
            self.idle_turns = 0
            self.nav.go(ct, best_ore, lambda d: step_conv(ct, d))
            return

        self.idle_turns += 1

        self._try_repair(ct, pos)

        self.explore_turns += 1
        if self.explore_turns > 30 or (
            self.target and pos.distance_squared(self.target) <= 4
        ):
            self._new_explore_target(ct)

        if self.target:
            self.nav.go(ct, self.target, lambda d: step_conv(ct, d))

    def _try_build_gunner(self, ct: Controller, pos: Position) -> bool:
        my = ct.get_team()
        enemy_dir = toward(self.core, self.enemy_core)

        for t in ct.get_nearby_tiles():
            if pos.distance_squared(t) > GameConstants.ACTION_RADIUS_SQ:
                continue
            if wall(ct, t) or ct.get_tile_building_id(t) is not None:
                continue

            has_feed = False
            edx, edy = enemy_dir.delta()
            for fd in DIRS:
                fp = t.add(fd)
                adj_dx = fp.x - t.x
                adj_dy = fp.y - t.y
                if adj_dx == edx and adj_dy == edy:
                    continue
                if not ib(ct, fp):
                    continue
                fbid = ct.get_tile_building_id(fp)
                if fbid is None:
                    continue
                if ct.get_team(fbid) != my:
                    continue
                fet = ct.get_entity_type(fbid)
                if fet in (
                    EntityType.CONVEYOR,
                    EntityType.ARMOURED_CONVEYOR,
                    EntityType.SPLITTER,
                    EntityType.HARVESTER,
                ):
                    has_feed = True
                    break

            if has_feed and ct.can_build_gunner(t, enemy_dir):
                ct.build_gunner(t, enemy_dir)
                self.gunners_built += 1
                return True
        return False

    def _try_repair(self, ct: Controller, pos: Position) -> None:
        my = ct.get_team()
        for t in ct.get_nearby_tiles():
            bid = ct.get_tile_building_id(t)
            if bid is None or ct.get_team(bid) != my:
                continue
            et = ct.get_entity_type(bid)
            if et not in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR):
                continue
            dd = ct.get_direction(bid)
            dx, dy = dd.delta()
            out = Position(t.x + dx, t.y + dy)
            if not ib(ct, out) or not ct.is_in_vision(out):
                continue
            if ct.get_tile_building_id(out) is not None:
                continue
            if ct.get_tile_env(out) == Environment.WALL:
                continue
            if (
                self.core
                and abs(out.x - self.core.x) <= 1
                and abs(out.y - self.core.y) <= 1
            ):
                continue
            if pos.distance_squared(out) <= GameConstants.ACTION_RADIUS_SQ:
                best_dir = toward(out, self.core)
                if ct.can_build_conveyor(out, best_dir):
                    ct.build_conveyor(out, best_dir)
                    return
            break

    def _new_explore_target(self, ct: Controller) -> None:
        if not self.core or not self.spoke_dir:
            return
        w = ct.get_map_width()
        h = ct.get_map_height()
        pos = ct.get_position()

        dx, dy = self.spoke_dir.delta()
        dist = random.randint(8, max(w, h) // 2)
        tx = max(1, min(w - 2, pos.x + dx * dist + random.randint(-3, 3)))
        ty = max(1, min(h - 2, pos.y + dy * dist + random.randint(-3, 3)))
        self.target = Position(tx, ty)
        self.explore_turns = 0
        self.nav.reset()

    def _raid(self, ct: Controller) -> None:
        if not self.core:
            return
        pos = ct.get_position()
        my = ct.get_team()

        best = None
        best_prio = -1
        best_dist = 999999

        for eid in ct.get_nearby_entities():
            if ct.get_team(eid) == my:
                continue
            et = ct.get_entity_type(eid)
            ep = ct.get_position(eid)
            d = pos.distance_squared(ep)

            prio = 0
            if et in (
                EntityType.CONVEYOR,
                EntityType.ARMOURED_CONVEYOR,
                EntityType.SPLITTER,
                EntityType.BRIDGE,
            ):
                prio = 10
            elif et == EntityType.HARVESTER:
                prio = 8
            elif et == EntityType.FOUNDRY:
                prio = 7
            elif et == EntityType.CORE:
                prio = 2

            if prio > best_prio or (prio == best_prio and d < best_dist):
                best_prio = prio
                best_dist = d
                best = ep

        if best:
            if pos.distance_squared(best) == 0:
                ct.self_destruct()
                return
            self.nav.go(ct, best, lambda d: step_raid(ct, d))
            return

        w = ct.get_map_width()
        h = ct.get_map_height()
        enemy_core = Position(w - 1 - self.core.x, h - 1 - self.core.y)

        if pos.distance_squared(enemy_core) <= 2:
            ct.self_destruct()
            return

        self.nav.go(ct, enemy_core, lambda d: step_raid(ct, d))


class TurretUnit:
    def run(self, ct: Controller) -> None:
        my = ct.get_team()
        best_target = None
        best_prio = -1

        for eid in ct.get_nearby_entities():
            if ct.get_team(eid) == my:
                continue
            epos = ct.get_position(eid)
            if not ct.can_fire(epos):
                continue
            et = ct.get_entity_type(eid)
            prio = 0
            if et == EntityType.BUILDER_BOT:
                prio = 10
            elif et == EntityType.HARVESTER:
                prio = 5
            else:
                prio = 1
            if prio > best_prio:
                best_prio = prio
                best_target = epos

        if best_target:
            ct.fire(best_target)


class Player:
    def __init__(self) -> None:
        self.core_bot = CoreBot()
        self.builder = BuilderAgent()
        self.turret = TurretUnit()

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            self.core_bot.run(ct)
        elif etype == EntityType.BUILDER_BOT:
            self.builder.run(ct)
        elif etype in (EntityType.GUNNER, EntityType.SENTINEL, EntityType.BREACH):
            self.turret.run(ct)
