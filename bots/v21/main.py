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
        self.wf = False
        self.ws = 1
        self.wf_start: tuple[int, int] | None = None
        self.wf_start_dist = 999999
        self.mline_start: tuple[int, int] | None = None
        self.prev_target: tuple[int, int] | None = None
        self.last_dir: Direction | None = None
        self.wf_turns = 0
        self.recent: list[tuple[int, int]] = []
        self.unreachable = False

    def reset(self) -> None:
        self.__init__()

    def _on_mline(self, px: int, py: int, tx: int, ty: int) -> bool:
        if self.mline_start is None:
            return True
        sx, sy = self.mline_start
        dx, dy = tx - sx, ty - sy
        cross = dx * (py - sy) - dy * (px - sx)
        length = max(abs(dx), abs(dy), 1)
        return abs(cross) <= length

    def go(self, ct: Controller, target: Position, step_fn) -> bool:
        pos = ct.get_position()

        if (
            self.prev_target is None
            or target.x != self.prev_target[0]
            or target.y != self.prev_target[1]
        ):
            self.reset()
            self.prev_target = (target.x, target.y)
            self.mline_start = (pos.x, pos.y)

        self.recent.append((pos.x, pos.y))
        if len(self.recent) > 8:
            self.recent.pop(0)
        if len(self.recent) >= 8 and len(set(self.recent)) <= 2:
            self.ws = -self.ws
            self.wf = not self.wf
            self.recent.clear()
            self.unreachable = True
            return False

        dist = pos.distance_squared(target)
        d = toward(pos, target)

        if not self.wf:
            if step_fn(d):
                return True
            self.wf = True
            self.wf_start = (pos.x, pos.y)
            self.wf_start_dist = dist
            self.last_dir = d
            self.wf_turns = 0

        self.wf_turns += 1

        if self.wf_turns > 1 and (pos.x, pos.y) != self.wf_start:
            exit_wf = False
            if (
                dist < self.wf_start_dist
                and self._on_mline(
                    pos.x,
                    pos.y,
                    target.x,
                    target.y,
                )
            ) or dist < self.wf_start_dist - 4:
                exit_wf = True
            if exit_wf:
                self.wf = False
                if step_fn(d):
                    return True
                self.wf = True
                self.wf_start = (pos.x, pos.y)
                self.wf_start_dist = dist
                self.last_dir = d
                self.wf_turns = 0

        if self.wf_turns > 2 and self.wf_start == (pos.x, pos.y):
            self.ws = -self.ws
            self.wf = False
            return False

        scan = d
        for _ in range(8):
            if step_fn(scan):
                self.last_dir = scan
                return True
            scan = scan.rotate_right() if self.ws == 1 else scan.rotate_left()

        return False


# --- Step functions ---


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


def step_conv(ct: Controller, d: Direction) -> bool:
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


# --- Core ---


class CoreBot:
    def __init__(self) -> None:
        self.spawned = 0

    def run(self, ct: Controller) -> None:
        ti, _ = ct.get_global_resources()
        cost = ct.get_builder_bot_cost()[0]
        rnd = ct.get_current_round()
        core_pos = ct.get_position()
        my = ct.get_team()

        for eid in ct.get_nearby_entities():
            if (
                ct.get_team(eid) != my
                and ct.get_entity_type(eid) == EntityType.BUILDER_BOT
            ):
                if core_pos.distance_squared(ct.get_position(eid)) <= 36:
                    if ti >= cost:
                        for d in DIRS:
                            sp = core_pos.add(d)
                            if ct.can_spawn(sp):
                                ct.spawn_builder(sp)
                                self.spawned += 1
                                return
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
                self.spawned += 1
                return


# --- Builder states ---

EXPLORE = 0
SEEK_ORE = 1
RETURN = 2
CHAIN_BUILD = 3
MAINTAIN = 4
PATROL = 5
RAID = 6
FORTIFY = 7


class BuilderAgent:
    def __init__(self) -> None:
        self.core: Position | None = None
        self.enemy_core: Position | None = None
        self.nav = BugNav()
        self.state = EXPLORE
        self.init_done = False
        self.spoke_dir: Direction | None = None
        self.builder_id = 0
        self.has_income = False
        self.last_ti = 0
        self.visited_ore: set[tuple[int, int]] = set()
        self.target: Position | None = None
        self.ore_target: Position | None = None
        self.explore_turns = 0
        self.idle_turns = 0
        self.harvesters_built = 0
        self.fortify_step = 0
        self.fortify_target: Position | None = None
        self.fortify_dir: Direction | None = None
        self.has_fortified = False

    def _setup(self, ct: Controller) -> None:
        pos = ct.get_position()
        rnd = ct.get_current_round()
        for eid in ct.get_nearby_entities():
            if (
                ct.get_entity_type(eid) == EntityType.CORE
                and ct.get_team(eid) == ct.get_team()
            ):
                self.core = ct.get_position(eid)
                break

        if self.core:
            self.spoke_dir = toward(self.core, pos)
            w, h = ct.get_map_width(), ct.get_map_height()
            self.enemy_core = Position(w - 1 - self.core.x, h - 1 - self.core.y)

        if self.spoke_dir is None or self.spoke_dir == Direction.CENTRE:
            self.spoke_dir = random.choice(DIRS)

        if rnd >= RAID_START:
            self.state = RAID

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

        if self.state not in (RAID, CHAIN_BUILD, RETURN):
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
        elif self.state == RETURN:
            self._do_return(ct, pos)
        elif self.state == CHAIN_BUILD:
            self._do_chain_build(ct, pos)
        elif self.state == MAINTAIN:
            self._do_maintain(ct, pos)
        elif self.state == PATROL:
            self._do_patrol(ct, pos)
        elif self.state == FORTIFY:
            self._do_fortify(ct, pos)
        elif self.state == RAID:
            self._do_raid(ct, pos)

    # --- Helpers ---

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

    def _explore_dir(self, ct: Controller, pos: Position) -> Direction:
        my = ct.get_team()
        best = None
        best_score = 999
        for d in DIRS:
            score = 0
            dx, dy = d.delta()
            for r in range(1, 5):
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
        w, h = ct.get_map_width(), ct.get_map_height()
        dx, dy = d.delta()
        dist = random.randint(6, max(w, h) // 3)
        tx = max(1, min(w - 2, pos.x + dx * dist + random.randint(-2, 2)))
        ty = max(1, min(h - 2, pos.y + dy * dist + random.randint(-2, 2)))
        self.target = Position(tx, ty)
        self.explore_turns = 0
        self.nav.reset()

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

    def _find_frontline_conv(self, ct: Controller, pos: Position) -> Position | None:
        assert self.core is not None
        assert self.enemy_core is not None
        my = ct.get_team()
        mid_x = (self.core.x + self.enemy_core.x) // 2
        mid_y = (self.core.y + self.enemy_core.y) // 2
        mid = Position(mid_x, mid_y)
        best = None
        best_dist = 999999
        for t in ct.get_nearby_tiles():
            bid = ct.get_tile_building_id(t)
            if bid is None or ct.get_team(bid) != my:
                continue
            et = ct.get_entity_type(bid)
            if et != EntityType.CONVEYOR:
                continue
            if t.distance_squared(self.core) <= 4:
                continue
            d = t.distance_squared(mid)
            if d < best_dist:
                best_dist = d
                best = t
        return best

    # --- States ---

    def _do_explore(self, ct: Controller, pos: Position) -> None:
        adj = self._find_adj_ore(ct, pos)
        if adj:
            self.visited_ore.add((adj.x, adj.y))
            self.ore_target = adj
            self.state = RETURN
            self.nav.reset()
            return

        ore = self._find_visible_ore(ct, pos)
        if ore:
            self.state = SEEK_ORE
            self.target = ore
            self.nav.reset()
            return

        self.idle_turns += 1
        if self.has_income and self.idle_turns >= IDLE_BEFORE_RAID:
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
            self.nav.go(ct, self.target, lambda d: step_road(ct, d))
            if self.nav.unreachable:
                self.nav.unreachable = False
                self._new_explore_target(ct, ct.get_position())

    def _do_seek_ore(self, ct: Controller, pos: Position) -> None:
        adj = self._find_adj_ore(ct, pos)
        if adj:
            self.visited_ore.add((adj.x, adj.y))
            self.ore_target = adj
            self.state = RETURN
            self.nav.reset()
            return

        if self.target is None:
            self.state = EXPLORE
            return

        if ct.is_in_vision(self.target) and (
            not ore_env(ct, self.target)
            or ct.get_tile_building_id(self.target) is not None
        ):
            ore = self._find_visible_ore(ct, pos)
            if ore:
                self.target = ore
                self.nav.reset()
            else:
                self.state = EXPLORE
                self._new_explore_target(ct, pos)
            return

        self.nav.go(ct, self.target, lambda d: step_road(ct, d))
        if self.nav.unreachable:
            self.nav.unreachable = False
            self.state = EXPLORE
            self._new_explore_target(ct, ct.get_position())

    def _do_return(self, ct: Controller, pos: Position) -> None:
        assert self.core is not None
        if pos.distance_squared(self.core) <= 2:
            self.state = CHAIN_BUILD
            self.nav.reset()
            return

        self.nav.go(ct, self.core, lambda d: step_walk(ct, d))

    def _do_chain_build(self, ct: Controller, pos: Position) -> None:
        if not self.ore_target:
            self.state = EXPLORE
            return

        if ct.can_build_harvester(self.ore_target):
            ct.build_harvester(self.ore_target)
            self.harvesters_built += 1
            self.state = MAINTAIN
            self.idle_turns = 0
            self.ore_target = None
            return

        if ct.is_in_vision(self.ore_target) and (
            not ore_env(ct, self.ore_target)
            or ct.get_tile_building_id(self.ore_target) is not None
        ):
            self.ore_target = None
            self.state = EXPLORE
            self._new_explore_target(ct, pos)
            return

        self.nav.go(ct, self.ore_target, lambda d: step_conv(ct, d))
        if self.nav.unreachable:
            self.nav.unreachable = False
            self.ore_target = None
            self.state = EXPLORE
            self._new_explore_target(ct, ct.get_position())

    def _do_maintain(self, ct: Controller, pos: Position) -> None:
        brk = self._find_break(ct)
        if brk:
            if pos.distance_squared(brk) <= GameConstants.ACTION_RADIUS_SQ:
                d = repair_dir(ct, brk, self.core)
                if ct.can_build_conveyor(brk, d):
                    ct.build_conveyor(brk, d)
                    return
            self.nav.go(ct, brk, lambda d: step_walk(ct, d))
            return

        assert self.core is not None
        ti, _ = ct.get_global_resources()
        rnd = ct.get_current_round()

        if (
            self.harvesters_built >= 1
            and ti > 200
            and rnd > 100
            and not self.has_fortified
        ):
            fl = self._find_frontline_conv(ct, pos)
            if fl:
                self.fortify_target = fl
                self.fortify_step = 1
                self.state = FORTIFY
                self.nav.reset()
                return

        self.idle_turns += 1
        if self.idle_turns >= IDLE_BEFORE_RAID and self.has_income:
            self.state = RAID
            self.nav.reset()
            return

        if self.idle_turns > 20:
            self.state = PATROL
            self._new_explore_target(ct, ct.get_position())

    def _do_fortify(self, ct: Controller, pos: Position) -> None:
        assert self.core is not None and self.enemy_core is not None
        if not self.fortify_target:
            self.state = MAINTAIN
            self.idle_turns = 0
            return

        if self.fortify_step == 1:
            if (
                pos.distance_squared(self.fortify_target)
                > GameConstants.ACTION_RADIUS_SQ
            ):
                self.nav.go(ct, self.fortify_target, lambda d: step_walk(ct, d))
                return
            bid = ct.get_tile_building_id(self.fortify_target)
            if bid is None:
                self.fortify_target = None
                self.state = MAINTAIN
                self.idle_turns = 0
                return
            self.fortify_dir = ct.get_direction(bid)
            ct.destroy(self.fortify_target)
            self.fortify_step = 2
            return

        if self.fortify_step == 2:
            assert self.fortify_dir is not None
            if ct.can_build_splitter(self.fortify_target, self.fortify_dir):
                ct.build_splitter(self.fortify_target, self.fortify_dir)
                self.fortify_step = 3
            else:
                self.fortify_target = None
                self.state = MAINTAIN
                self.idle_turns = 0
            return

        if self.fortify_step == 3:
            assert self.fortify_dir is not None
            enemy_dir = toward(self.fortify_target, self.enemy_core)
            for try_d in [
                self.fortify_dir.rotate_left().rotate_left(),
                self.fortify_dir.rotate_right().rotate_right(),
                self.fortify_dir.rotate_left(),
                self.fortify_dir.rotate_right(),
            ]:
                gun_pos = self.fortify_target.add(try_d)
                if not ib(ct, gun_pos) or wall(ct, gun_pos):
                    continue
                if ct.get_tile_building_id(gun_pos) is not None:
                    continue
                if pos.distance_squared(gun_pos) > GameConstants.ACTION_RADIUS_SQ:
                    self.nav.go(ct, gun_pos, lambda d: step_walk(ct, d))
                    return
                if ct.can_build_gunner(gun_pos, enemy_dir):
                    ct.build_gunner(gun_pos, enemy_dir)
                    self.fortify_target = None
                    self.fortify_step = 0
                    self.has_fortified = True
                    self.state = MAINTAIN
                    self.idle_turns = 0
                    return

            self.fortify_target = None
            self.fortify_step = 0
            self.has_fortified = True
            self.state = MAINTAIN
            self.idle_turns = 0

    def _do_patrol(self, ct: Controller, pos: Position) -> None:
        adj = self._find_adj_ore(ct, pos)
        if adj:
            self.visited_ore.add((adj.x, adj.y))
            self.ore_target = adj
            self.state = RETURN
            self.nav.reset()
            return

        ore = self._find_visible_ore(ct, pos)
        if ore:
            self.state = SEEK_ORE
            self.target = ore
            self.nav.reset()
            return

        brk = self._find_break(ct)
        if brk:
            self.state = MAINTAIN
            self.idle_turns = 0
            return

        if self.has_income and self.idle_turns >= IDLE_BEFORE_RAID:
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
        assert self.core is not None and self.enemy_core is not None
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

        past_midpoint = pos.distance_squared(self.enemy_core) < pos.distance_squared(
            self.core,
        )

        if past_midpoint:
            best = None
            best_dist = 999999
            for eid in ct.get_nearby_entities():
                if ct.get_team(eid) == my:
                    continue
                et = ct.get_entity_type(eid)
                if et not in (
                    EntityType.CONVEYOR,
                    EntityType.ARMOURED_CONVEYOR,
                    EntityType.SPLITTER,
                    EntityType.HARVESTER,
                    EntityType.FOUNDRY,
                    EntityType.BRIDGE,
                ):
                    continue
                ep = ct.get_position(eid)
                d = ep.distance_squared(self.enemy_core)
                if d < best_dist:
                    best_dist = d
                    best = ep

            if best:
                self.nav.go(ct, best, lambda d: step_raid(ct, d))
                return

        self.nav.go(ct, self.enemy_core, lambda d: step_raid(ct, d))


# --- Turret ---


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


# --- Player ---


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
