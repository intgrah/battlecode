import random
from collections.abc import Callable

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
RAID_START = 200
IDLE_BEFORE_RAID = 60
RAIDER_IDS = {6, 7}

SPOKES = [
    Direction.NORTH,
    Direction.EAST,
    Direction.SOUTH,
    Direction.WEST,
    Direction.NORTHEAST,
    Direction.SOUTHEAST,
    Direction.SOUTHWEST,
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


def diagonalize(d: Direction) -> Direction:
    dx, dy = d.delta()
    if dx == 0 and dy != 0:
        return Direction.NORTHEAST if dy < 0 else Direction.SOUTHEAST
    if dy == 0 and dx != 0:
        return Direction.NORTHEAST if dx > 0 else Direction.SOUTHWEST
    return d


class BugNav:
    def __init__(self) -> None:
        self.lp = None
        self.stuck = 0
        self.wf = False
        self.ws = 1
        self.cl = 999999

    def reset(self) -> None:
        self.__init__()

    def go(
        self,
        ct: Controller,
        target: Position,
        step_fn: Callable[[Direction], bool],
    ) -> bool:
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


def step_walk(ct: Controller, d: Direction) -> bool:
    if wall(ct, ct.get_position().add(d)):
        return False
    if ct.can_move(d):
        ct.move(d)
        return True
    return False


def repair_dir(ct: Controller, gap: Position, core: Position) -> Direction:
    my = ct.get_team()
    best_dir = None
    best_core_dist = 999999

    for d in DIRS:
        adj = gap.add(d)
        if not ib(ct, adj) or not ct.is_in_vision(adj):
            continue
        bid = ct.get_tile_building_id(adj)
        if bid is None or ct.get_team(bid) != my:
            continue
        et = ct.get_entity_type(bid)
        if et not in (
            EntityType.CONVEYOR,
            EntityType.ARMOURED_CONVEYOR,
            EntityType.SPLITTER,
        ):
            continue
        conv_out = ct.get_direction(bid)
        ox, oy = conv_out.delta()
        out_pos = Position(adj.x + ox, adj.y + oy)
        if out_pos.x == gap.x and out_pos.y == gap.y:
            continue
        dist = adj.distance_squared(core)
        if dist < best_core_dist:
            best_core_dist = dist
            best_dir = d

    if best_dir:
        return best_dir
    return toward(gap, core)


class CoreBot:
    def __init__(self) -> None:
        self.spawned = 0

    def run(self, ct: Controller) -> None:
        ti, _ = ct.get_global_resources()
        cost = ct.get_builder_bot_cost()[0]
        rnd = ct.get_current_round()
        core_pos = ct.get_position()
        my = ct.get_team()

        enemy_nearby = False
        for eid in ct.get_nearby_entities():
            if (
                ct.get_team(eid) != my
                and ct.get_entity_type(eid) == EntityType.BUILDER_BOT
            ) and core_pos.distance_squared(ct.get_position(eid)) <= 36:
                enemy_nearby = True
                break

        if enemy_nearby and ti >= cost:
            for d in DIRS:
                sp = core_pos.add(d)
                if ct.can_spawn(sp):
                    ct.spawn_builder(sp)
                    if ct.can_place_marker(sp):
                        ct.place_marker(sp, mk_id(self.spawned))
                    self.spawned += 1
                    return

        if self.spawned < NUM_INITIAL:
            if ti < cost + ct.get_harvester_cost()[0]:
                return
        elif rnd < RAID_START or ti < 500:
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
        self.sentinel_built = False

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

        rnd = ct.get_current_round()
        if not self.raiding and (
            (self.builder_id in RAIDER_IDS and rnd >= RAID_START)
            or (self.idle_turns >= IDLE_BEFORE_RAID and self.has_income)
        ):
            self.raiding = True
            self.nav.reset()

        if self.raiding:
            self._raid(ct)
        else:
            self._economy(ct)

    def _economy(self, ct: Controller) -> None:
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
            ) and ct.can_build_harvester(t):
                ct.build_harvester(t)
                self.visited_ore.add((t.x, t.y))
                self.idle_turns = 0
                self.harvesters_built += 1
                self._new_explore_target(ct)
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

        if self._try_build_sentinel(ct, pos):
            return

        brk = self._find_break(ct)
        if brk and pos.distance_squared(brk) <= GameConstants.ACTION_RADIUS_SQ:
            assert self.core is not None
            d = repair_dir(ct, brk, self.core)
            if ct.can_build_conveyor(brk, d):
                ct.build_conveyor(brk, d)
                return

        self.idle_turns += 1
        self.explore_turns += 1
        if self.explore_turns > 40 or (
            self.target and pos.distance_squared(self.target) <= 4
        ):
            self.spoke_dir = random.choice(DIRS)
            self._new_explore_target(ct)

        if self.target:
            self.nav.go(ct, self.target, lambda d: step_conv(ct, d))

    def _find_break(self, ct: Controller) -> Position | None:
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
            if wall(ct, out):
                continue
            if (
                self.core
                and abs(out.x - self.core.x) <= 1
                and abs(out.y - self.core.y) <= 1
            ):
                continue
            return out
        return None

    def _try_build_sentinel(self, ct: Controller, pos: Position) -> bool:
        if self.sentinel_built or not self.enemy_core or not self.core:
            return False
        if not self.has_income or self.harvesters_built < 1:
            return False
        ti, _ = ct.get_global_resources()
        if ti < ct.get_sentinel_cost()[0] + 100:
            return False
        if pos.distance_squared(self.core) > 20:
            return False

        my = ct.get_team()
        for eid in ct.get_nearby_entities():
            if (
                ct.get_entity_type(eid) == EntityType.SENTINEL
                and ct.get_team(eid) == my
            ):
                self.sentinel_built = True
                return False

        face = diagonalize(toward(self.core, self.enemy_core))
        fdx, fdy = face.delta()

        best_tile = None
        best_feeders = 0
        for t in ct.get_nearby_tiles(GameConstants.ACTION_RADIUS_SQ):
            if wall(ct, t) or ore_env(ct, t):
                continue
            if ct.get_tile_building_id(t) is not None:
                continue
            if not ct.can_build_sentinel(t, face):
                continue
            feeders = 0
            for d in DIRS:
                adj = t.add(d)
                if adj.x - t.x == fdx and adj.y - t.y == fdy:
                    continue
                if not ib(ct, adj):
                    continue
                abid = ct.get_tile_building_id(adj)
                if abid is None or ct.get_team(abid) != my:
                    continue
                if ct.get_entity_type(abid) in (
                    EntityType.CONVEYOR,
                    EntityType.ARMOURED_CONVEYOR,
                ):
                    adir = ct.get_direction(abid)
                    adx, ady = adir.delta()
                    if adj.x + adx == t.x and adj.y + ady == t.y:
                        feeders += 1
            if feeders > best_feeders:
                best_feeders = feeders
                best_tile = t

        if best_tile is None:
            for t in ct.get_nearby_tiles(GameConstants.ACTION_RADIUS_SQ):
                if wall(ct, t) or ore_env(ct, t):
                    continue
                if ct.get_tile_building_id(t) is not None:
                    continue
                if ct.can_build_sentinel(t, face):
                    best_tile = t
                    break

        if best_tile:
            ct.build_sentinel(best_tile, face)
            self.sentinel_built = True
            return True
        return False

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
        best = None
        best_prio = -1
        for eid in ct.get_nearby_entities():
            if ct.get_team(eid) == my:
                continue
            epos = ct.get_position(eid)
            if not ct.can_fire(epos):
                continue
            prio = 10 if ct.get_entity_type(eid) == EntityType.BUILDER_BOT else 1
            if prio > best_prio:
                best_prio = prio
                best = epos
        if best:
            ct.fire(best)


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
