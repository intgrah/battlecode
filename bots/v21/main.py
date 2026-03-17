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

NUM_INITIAL = 4
RAID_START = 200
IDLE_BEFORE_RAID = 60
RAIDER_IDS = {6, 7}

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

TAG_SPAWN = 0 << 30
TAG_MASK = 0xC000_0000


def mk_spawn_tag(n: int) -> int:
    return TAG_SPAWN | (n & 0xFF)


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


def step_road(ct: Controller, d: Direction) -> bool:
    nxt = ct.get_position().add(d)
    if wall(ct, nxt):
        return False
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


def repair_dir(ct: Controller, gap: Position, core: Position) -> Direction:
    my = ct.get_team()
    best_dir = None
    best_core_dist = 999999
    upstream_dir = None

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
            upstream_dir = conv_out
            continue
        dist = adj.distance_squared(core)
        if dist < best_core_dist:
            best_core_dist = dist
            best_dir = d

    if best_dir:
        return best_dir
    if upstream_dir:
        return upstream_dir
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
                    ct.place_marker(sp, mk_spawn_tag(self.spawned))
                self.spawned += 1
                return


EXPLORE = 0
SEEK_ORE = 1
RETURN_TO_CORE = 2
CHAIN_BUILD = 3
MAINTAIN = 4
PATROL = 5
RAID = 6


class BuilderAgent:
    def __init__(self) -> None:
        self.core: Position | None = None
        self.enemy_core: Position | None = None
        self.nav = BugNav()
        self.target: Position | None = None
        self.init_done = False
        self.spoke_dir: Direction | None = None
        self.has_income = False
        self.last_ti = 0
        self.builder_id = 0
        self.visited_ore: set[tuple[int, int]] = set()
        self.explore_turns = 0
        self.idle_turns = 0
        self.state = EXPLORE
        self.harvesters_built = 0
        self.ore_target: Position | None = None
        self.path: list[tuple[int, int]] = []
        self.path_idx = 0

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
            if val & TAG_MASK == TAG_SPAWN:
                sid = val & 0xFF
                self.builder_id = sid
                if sid < len(SPOKES):
                    self.spoke_dir = SPOKES[sid]
                if sid >= NUM_INITIAL:
                    self.state = RAID

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

        pos = ct.get_position()

        if self.state not in (RAID, CHAIN_BUILD, RETURN_TO_CORE):
            bid = ct.get_tile_building_id(pos)
            if bid is not None and ct.get_team(bid) != ct.get_team():
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

        if self.state == EXPLORE:
            self._do_explore(ct, pos)
        elif self.state == SEEK_ORE:
            self._do_seek_ore(ct, pos)
        elif self.state == RETURN_TO_CORE:
            self._do_return(ct, pos)
        elif self.state == CHAIN_BUILD:
            self._do_chain_build(ct, pos)
        elif self.state == MAINTAIN:
            self._do_maintain(ct, pos)
        elif self.state == PATROL:
            self._do_patrol(ct, pos)
        elif self.state == RAID:
            self._do_raid(ct, pos)

    def _find_adj_ore(self, ct: Controller, pos: Position) -> Position | None:
        for d in Direction:
            t = pos.add(d)
            if not ib(ct, t):
                continue
            if (
                ore_env(ct, t)
                and ct.get_tile_building_id(t) is None
                and (t.x, t.y) not in self.visited_ore
            ):
                return t
        return None

    def _find_visible_ore(self, ct: Controller, pos: Position) -> Position | None:
        best = None
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
                    best = t
        return best

    def _try_harvest(self, ct: Controller, pos: Position) -> bool:
        adj = self._find_adj_ore(ct, pos)
        if adj and ct.can_build_harvester(adj):
            ct.build_harvester(adj)
            self.visited_ore.add((adj.x, adj.y))
            self.harvesters_built += 1
            self.idle_turns = 0
            return True
        return False

    def _explore_dir(self, ct: Controller, pos: Position) -> Direction:
        my = ct.get_team()
        best = None
        best_score = 999
        for d in DIRS:
            score = 0
            for r in range(1, 5):
                dx, dy = d.delta()
                check = Position(pos.x + dx * r, pos.y + dy * r)
                if not ib(ct, check) or not ct.is_in_vision(check):
                    score += 2
                    continue
                bid = ct.get_tile_building_id(check)
                if bid is not None and ct.get_team(bid) == my:
                    score += 1
            if score < best_score:
                best_score = score
                best = d
        return best or random.choice(DIRS)

    def _new_explore_target(self, ct: Controller, pos: Position) -> None:
        d = self._explore_dir(ct, pos)
        self.spoke_dir = d
        w, h = ct.get_map_width(), ct.get_map_height()
        dx, dy = d.delta()
        dist = random.randint(6, max(w, h) // 3)
        tx = max(1, min(w - 2, pos.x + dx * dist + random.randint(-2, 2)))
        ty = max(1, min(h - 2, pos.y + dy * dist + random.randint(-2, 2)))
        self.target = Position(tx, ty)
        self.explore_turns = 0
        self.nav.reset()

    def _move_and_record(self, ct: Controller, target: Position) -> bool:
        return self.nav.go(ct, target, lambda d: step_road(ct, d))

    def _start_scout(self) -> None:
        self.path.clear()
        self.path_idx = 0
        self.state = EXPLORE

    def _found_ore(self, ore_pos: Position) -> None:
        self.ore_target = ore_pos
        self.path.clear()
        self.state = RETURN_TO_CORE
        self.nav.reset()

    def _do_explore(self, ct: Controller, pos: Position) -> None:
        adj = self._find_adj_ore(ct, pos)
        if adj:
            self.visited_ore.add((adj.x, adj.y))
            self._found_ore(adj)
            return

        ore = self._find_visible_ore(ct, pos)
        if ore:
            self.state = SEEK_ORE
            self.target = ore
            self.nav.reset()
            return

        self.idle_turns += 1
        if self.has_income and (
            (self.builder_id in RAIDER_IDS and ct.get_current_round() >= RAID_START)
            or self.idle_turns >= IDLE_BEFORE_RAID
        ):
            self.state = RAID
            self.nav.reset()
            return

        self.explore_turns += 1
        if (
            self.explore_turns > 30
            or self.target is None
            or pos.distance_squared(self.target) <= 4
        ):
            self._new_explore_target(ct, pos)

        if self.target:
            self._move_and_record(ct, self.target)

    def _do_seek_ore(self, ct: Controller, pos: Position) -> None:
        adj = self._find_adj_ore(ct, pos)
        if adj:
            self.visited_ore.add((adj.x, adj.y))
            self._found_ore(adj)
            return

        if self.target is None:
            self._start_scout()
            return

        if (
            not ore_env(ct, self.target)
            or ct.get_tile_building_id(self.target) is not None
        ):
            ore = self._find_visible_ore(ct, pos)
            if ore:
                self.target = ore
                self.nav.reset()
            else:
                self._start_scout()
                self._new_explore_target(ct, pos)
            return

        self._move_and_record(ct, self.target)

    def _do_return(self, ct: Controller, pos: Position) -> None:
        if not self.core:
            self.state = EXPLORE
            return

        if pos.distance_squared(self.core) <= 2:
            self.path.append((pos.x, pos.y))
            self.path.reverse()
            self.path_idx = 0
            self.state = CHAIN_BUILD
            self.nav.reset()
            return

        before = (pos.x, pos.y)
        self.nav.go(ct, self.core, lambda d: step_walk(ct, d))
        after = ct.get_position()
        if (after.x, after.y) != before:
            self.path.append(before)

    def _step_conv(self, ct: Controller, d: Direction) -> bool:
        pos = ct.get_position()
        nxt = pos.add(d)
        if wall(ct, nxt):
            return False
        if not ore_env(ct, nxt):
            bid = ct.get_tile_building_id(nxt)
            if bid is not None and ct.get_entity_type(bid) == EntityType.ROAD:
                if ct.get_team(bid) == ct.get_team():
                    ct.destroy(nxt)
            if ct.can_build_conveyor(nxt, d.opposite()):
                ct.build_conveyor(nxt, d.opposite())
        if ct.can_move(d):
            ct.move(d)
            return True
        return False

    def _do_chain_build(self, ct: Controller, pos: Position) -> None:
        if not self.ore_target or self.path_idx >= len(self.path):
            self._start_scout()
            return

        if self.path_idx == len(self.path) - 1:
            if ct.can_build_harvester(self.ore_target):
                ct.build_harvester(self.ore_target)
                self.harvesters_built += 1
            self.state = MAINTAIN
            self.idle_turns = 0
            self.ore_target = None
            self.path.clear()
            return

        tx, ty = self.path[self.path_idx + 1]
        if pos.x == tx and pos.y == ty:
            self.path_idx += 1
            return
        d = toward(pos, Position(tx, ty))
        if self._step_conv(ct, d):
            new = ct.get_position()
            if (new.x, new.y) == (tx, ty):
                self.path_idx += 1
        else:
            self.path_idx += 1

    def _find_break(self, ct: Controller, pos: Position) -> Position | None:
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

    def _do_maintain(self, ct: Controller, pos: Position) -> None:
        brk = self._find_break(ct, pos)
        if brk:
            if pos.distance_squared(brk) <= GameConstants.ACTION_RADIUS_SQ:
                d = repair_dir(ct, brk, self.core)
                if ct.can_build_conveyor(brk, d):
                    ct.build_conveyor(brk, d)
                    return
            self.nav.go(ct, brk, lambda d: step_walk(ct, d))
            return

        self.idle_turns += 1
        if self.idle_turns >= IDLE_BEFORE_RAID and self.has_income:
            self.state = RAID
            self.nav.reset()
            return

        if self.idle_turns > 20:
            self.state = PATROL
            self._new_explore_target(ct, ct.get_position())

    def _do_patrol(self, ct: Controller, pos: Position) -> None:
        adj = self._find_adj_ore(ct, pos)
        if adj:
            self.visited_ore.add((adj.x, adj.y))
            self._found_ore(adj)
            return

        ore = self._find_visible_ore(ct, pos)
        if ore:
            self.state = SEEK_ORE
            self.target = ore
            self.nav.reset()
            return

        brk = self._find_break(ct, pos)
        if brk:
            self.state = MAINTAIN
            self.idle_turns = 0
            return

        if self.has_income:
            if (
                self.builder_id in RAIDER_IDS and ct.get_current_round() >= RAID_START
            ) or self.idle_turns >= IDLE_BEFORE_RAID:
                self.state = RAID
                self.nav.reset()
                return

        self.idle_turns += 1
        self.explore_turns += 1
        if (
            self.explore_turns > 30
            or self.target is None
            or pos.distance_squared(self.target) <= 4
        ):
            self._new_explore_target(ct, pos)
        if self.target:
            self.nav.go(ct, self.target, lambda d: step_road(ct, d))

    def _do_raid(self, ct: Controller, pos: Position) -> None:
        if not self.core:
            return
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

        if self.enemy_core:
            if pos.distance_squared(self.enemy_core) <= 2:
                ct.self_destruct()
                return
            self.nav.go(ct, self.enemy_core, lambda d: step_raid(ct, d))


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
