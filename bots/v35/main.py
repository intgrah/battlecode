import random
from collections import deque
from collections.abc import Callable

from cambc import (
    Controller,
    Direction,
    EntityType,
    Environment,
    GameConstants,
    Position,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DIRS = [
    Direction.NORTH,
    Direction.NORTHEAST,
    Direction.EAST,
    Direction.SOUTHEAST,
    Direction.SOUTH,
    Direction.SOUTHWEST,
    Direction.WEST,
    Direction.NORTHWEST,
]
CARDINALS = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]
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

_TRANSPORT = frozenset(
    {
        EntityType.CONVEYOR,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.SPLITTER,
        EntityType.BRIDGE,
    },
)
_INFRA = _TRANSPORT | {EntityType.HARVESTER, EntityType.FOUNDRY}

NUM_INITIAL_BUILDERS = 4
MAX_BUILDERS = 8  # overridden dynamically based on map size
IDLE_BEFORE_RAID = 200
PATROL_IDLE_LIMIT = 30
TI_WINDOW = 10
FORTIFY_MIN_HARVESTERS = 3
MAX_FORTIFY = 1
CONV_TI_THRESHOLD = 200

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


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


_DELTA_TO_DIR = {d.delta(): d for d in DIRS}


def _is_diagonal(d: Direction) -> bool:
    dx, dy = d.delta()
    return dx != 0 and dy != 0


# ---------------------------------------------------------------------------
# Step functions
# ---------------------------------------------------------------------------


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
    if _is_diagonal(d):
        dx, dy = d.delta()
        pair = [_DELTA_TO_DIR[(dx, 0)], _DELTA_TO_DIR[(0, dy)]]
        if random.random() < 0.5:
            pair.reverse()
        return any(step_conv(ct, cd) for cd in pair)
    pos = ct.get_position()
    nxt = pos.add(d)
    if wall(ct, nxt):
        return False
    if not ore_env(ct, nxt):
        bid = ct.get_tile_building_id(nxt)
        if (
            bid is not None
            and ct.get_entity_type(bid) == EntityType.ROAD
            and ct.get_team(bid) == ct.get_team()
        ):
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
    for d in CARDINALS:
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
    d = toward(gap, core)
    dx, dy = d.delta()
    if dx != 0 and dy != 0:
        return _DELTA_TO_DIR[(dx, 0)]
    return d


# ---------------------------------------------------------------------------
# BugNav
# ---------------------------------------------------------------------------


class BugNav:
    def __init__(self) -> None:
        self.unreachable = False
        self.wf = False
        self.ws = 1
        self.wf_start: tuple[int, int] | None = None
        self.wf_start_dist = 999999
        self.mline_start: tuple[int, int] | None = None
        self.prev_target: tuple[int, int] | None = None
        self.wf_turns = 0
        self.recent: list[tuple[int, int]] = []

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

    def go(
        self,
        ct: Controller,
        target: Position,
        step_fn: Callable[[Direction], bool],
    ) -> bool:
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
            self.wf_turns = 0

        self.wf_turns += 1
        if self.wf_turns > 1 and (pos.x, pos.y) != self.wf_start:
            exit_wf = False
            if (
                dist < self.wf_start_dist
                and self._on_mline(pos.x, pos.y, target.x, target.y)
            ) or dist < self.wf_start_dist - 4:
                exit_wf = True
            if exit_wf:
                self.wf = False
                if step_fn(d):
                    return True
                self.wf = True
                self.wf_start = (pos.x, pos.y)
                self.wf_start_dist = dist
                self.wf_turns = 0

        if self.wf_turns > 2 and self.wf_start == (pos.x, pos.y):
            self.ws = -self.ws
            self.wf = False
            return False

        scan = d
        for _ in range(8):
            if step_fn(scan):
                return True
            scan = scan.rotate_right() if self.ws == 1 else scan.rotate_left()
        return False


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------


class CoreBot:
    def __init__(self) -> None:
        self.spawned = 0
        self.spoke_idx = 0
        self.ti_history: deque[int] = deque(maxlen=TI_WINDOW)
        self.defense_spawned_round = -100

    def _try_spawn(self, ct: Controller) -> bool:
        pos = ct.get_position()
        spoke = SPOKES[self.spoke_idx % len(SPOKES)]
        for d in [spoke, spoke.rotate_left(), spoke.rotate_right(), *DIRS]:
            sp = pos.add(d)
            if ct.can_spawn(sp):
                ct.spawn_builder(sp)
                self.spawned += 1
                self.spoke_idx += 2
                return True
        return False

    def _try_spawn_toward(self, ct: Controller, target_pos: Position) -> bool:
        pos = ct.get_position()
        d = toward(pos, target_pos)
        for try_d in [d, d.rotate_left(), d.rotate_right(), *DIRS]:
            sp = pos.add(try_d)
            if ct.can_spawn(sp):
                ct.spawn_builder(sp)
                self.spawned += 1
                return True
        return False

    def run(self, ct: Controller) -> None:
        ti, _ = ct.get_global_resources()
        cost, _ = ct.get_builder_bot_cost()
        rnd = ct.get_current_round()
        area = ct.get_map_width() * ct.get_map_height()
        max_b = min(MAX_BUILDERS, max(4, area // 150))

        if ti < cost:
            return

        my = ct.get_team()

        for eid in ct.get_nearby_entities():
            if ct.get_team(eid) == my:
                continue
            et = ct.get_entity_type(eid)
            if et in (
                EntityType.BUILDER_BOT,
                EntityType.GUNNER,
                EntityType.SENTINEL,
                EntityType.BREACH,
            ):
                ep = ct.get_position(eid)
                core_pos = ct.get_position()
                if (
                    ep.distance_squared(core_pos) <= 49
                    and rnd - self.defense_spawned_round >= 10
                ):
                    self._try_spawn_toward(ct, ep)
                    self.defense_spawned_round = rnd
                    return

        if self.spawned < NUM_INITIAL_BUILDERS:
            harv_cost, _ = ct.get_harvester_cost()
            if ti < cost + harv_cost:
                return
            self._try_spawn(ct)
            return

        if self.spawned >= max_b:
            return

        self.ti_history.append(ti)
        if len(self.ti_history) < TI_WINDOW:
            return
        ti_delta = self.ti_history[-1] - self.ti_history[0]
        if ti_delta > cost * 2 and ti > cost * 4:
            self._try_spawn(ct)


# ---------------------------------------------------------------------------
# Builder — priority-based, no explicit states
# ---------------------------------------------------------------------------


class BuilderAgent:
    def __init__(self) -> None:
        self.core: Position | None = None
        self.enemy_core: Position | None = None
        self.w = 0
        self.h = 0
        self.nav = BugNav()
        self.init_done = False
        self.spoke_dir: Direction | None = None
        self.target: Position | None = None
        self.visited_ore: set[tuple[int, int]] = set()

    def _setup(self, ct: Controller) -> None:
        my = ct.get_team()
        self.w, self.h = ct.get_map_width(), ct.get_map_height()
        for eid in ct.get_nearby_entities():
            if ct.get_entity_type(eid) == EntityType.CORE and ct.get_team(eid) == my:
                self.core = ct.get_position(eid)
                break
        if self.core:
            self.enemy_core = Position(self.w - 1 - self.core.x, self.h - 1 - self.core.y)
            self.spoke_dir = toward(self.core, ct.get_position())
        if self.spoke_dir is None or self.spoke_dir == Direction.CENTRE:
            self.spoke_dir = random.choice(DIRS)
        self.init_done = True

    def _find_adj_ore(self, ct: Controller, pos: Position) -> Position | None:
        for d in DIRS:
            t = pos.add(d)
            if not ib(ct, t):
                continue
            if ore_env(ct, t) and ct.get_tile_building_id(t) is None and (t.x, t.y) not in self.visited_ore:
                return t
        return None

    def _find_visible_ore(self, ct: Controller, pos: Position) -> Position | None:
        best = None
        best_d = 999999
        for t in ct.get_nearby_tiles():
            if ore_env(ct, t) and ct.get_tile_building_id(t) is None and (t.x, t.y) not in self.visited_ore:
                d = pos.distance_squared(t)
                if d < best_d:
                    best_d = d
                    best = t
        return best

    def _find_break(self, ct: Controller) -> Position | None:
        my = ct.get_team()
        assert self.core is not None
        cx, cy = self.core.x, self.core.y
        for t in ct.get_nearby_tiles():
            bid = ct.get_tile_building_id(t)
            if bid is None or ct.get_team(bid) != my:
                continue
            et = ct.get_entity_type(bid)
            if et not in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR, EntityType.SPLITTER):
                continue
            dd = ct.get_direction(bid)
            dx, dy = dd.delta()
            out = Position(t.x + dx, t.y + dy)
            if not ib(ct, out) or not ct.is_in_vision(out):
                continue
            if wall(ct, out):
                continue
            if abs(out.x - cx) <= 1 and abs(out.y - cy) <= 1:
                continue
            out_bid = ct.get_tile_building_id(out)
            if out_bid is not None:
                continue
            return out
        return None

    def _has_cardinal_conv(self, ct: Controller, ore: Position) -> bool:
        my = ct.get_team()
        for d in CARDINALS:
            adj = ore.add(d)
            if not ib(ct, adj):
                continue
            bid = ct.get_tile_building_id(adj)
            if bid is not None and ct.get_team(bid) == my and ct.get_entity_type(bid) in _TRANSPORT:
                return True
        return False

    def _pick_target(self, ct: Controller, pos: Position) -> Position:
        my = ct.get_team()
        best = None
        best_score = -999
        for d in DIRS:
            score = 0
            dx, dy = d.delta()
            for r in range(1, 6):
                check = Position(pos.x + dx * r, pos.y + dy * r)
                if not ib(ct, check):
                    score -= 3
                    continue
                if not ct.is_in_vision(check):
                    score += 2
                    continue
                bid = ct.get_tile_building_id(check)
                if bid is not None and ct.get_team(bid) == my:
                    score -= 1
                else:
                    score += 1
            if score > best_score:
                best_score = score
                best = d
        d = best or random.choice(DIRS)
        dx, dy = d.delta()
        dist = random.randint(8, max(9, max(self.w, self.h) // 2))
        tx = max(1, min(self.w - 2, pos.x + dx * dist + random.randint(-3, 3)))
        ty = max(1, min(self.h - 2, pos.y + dy * dist + random.randint(-3, 3)))
        return Position(tx, ty)

    def run(self, ct: Controller) -> None:
        if not self.init_done:
            self._setup(ct)
        if not self.core:
            return

        pos = ct.get_position()
        my = ct.get_team()

        # P0: Self-destruct on enemy infra
        bid = ct.get_tile_building_id(pos)
        if bid is not None and ct.get_team(bid) != my:
            et = ct.get_entity_type(bid)
            if et in _INFRA:
                ct.self_destruct()
                return

        adj_ore = self._find_adj_ore(ct, pos)
        if adj_ore:
            if self._has_cardinal_conv(ct, adj_ore):
                if ct.can_build_harvester(adj_ore):
                    ct.build_harvester(adj_ore)
                    self.visited_ore.add((adj_ore.x, adj_ore.y))
                return
            for d in CARDINALS:
                adj = adj_ore.add(d)
                if not ib(ct, adj):
                    continue
                out_dir = adj.direction_to(pos)
                if ct.can_build_conveyor(adj, out_dir):
                    ct.build_conveyor(adj, out_dir)
                    return
            self.visited_ore.add((adj_ore.x, adj_ore.y))

        # P2: Repair break in vision
        brk = self._find_break(ct)
        if brk:
            if pos.distance_squared(brk) <= GameConstants.ACTION_RADIUS_SQ:
                bid_brk = ct.get_tile_building_id(brk)
                if bid_brk is not None and ct.get_entity_type(bid_brk) in (EntityType.ROAD, EntityType.MARKER):
                    ct.destroy(brk)
                d = repair_dir(ct, brk, self.core)
                if ct.can_build_conveyor(brk, d):
                    ct.build_conveyor(brk, d)
                return
            self.nav.go(ct, brk, lambda d: step_conv(ct, d))
            return

        # P3: Heal core if enemy turret nearby and we're adjacent
        for eid in ct.get_nearby_entities():
            if ct.get_team(eid) == my:
                continue
            et = ct.get_entity_type(eid)
            if et in (EntityType.GUNNER, EntityType.SENTINEL, EntityType.BREACH):
                ep = ct.get_position(eid)
                if ep.distance_squared(self.core) <= 49:
                    if pos.distance_squared(self.core) <= GameConstants.ACTION_RADIUS_SQ and ct.can_heal(self.core):
                        ct.heal(self.core)
                        return
                    break

        ore = self._find_visible_ore(ct, pos)
        if ore:
            if self.target is None or (not self.nav.wf and self.target != ore):
                self.target = ore
                self.nav.reset()
            self.nav.go(ct, self.target, lambda d: step_conv(ct, d))
            if self.nav.unreachable:
                self.visited_ore.add((self.target.x, self.target.y))
                self.nav.unreachable = False
                self.target = None
            return

        # P5: Explore
        if self.target is None or pos == self.target or self.nav.unreachable:
            self.nav.unreachable = False
            if self.target is None:
                d = self.spoke_dir
                assert d is not None
                dx, dy = d.delta()
                self.target = Position(
                    max(1, min(self.w - 2, pos.x + dx * self.w)),
                    max(1, min(self.h - 2, pos.y + dy * self.h)),
                )
            else:
                self.target = self._pick_target(ct, pos)
            self.nav.reset()
        self.nav.go(ct, self.target, lambda d: step_conv(ct, d))

# ---------------------------------------------------------------------------


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
            et = ct.get_entity_type(eid)
            prio = 10 if et == EntityType.BUILDER_BOT else 1
            if prio > best_prio:
                best_prio = prio
                best = epos
        if best:
            ct.fire(best)


# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------


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
