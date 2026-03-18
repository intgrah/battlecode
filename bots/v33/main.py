"""v33 — Unstoppable economy + anti-cheese defense.

Combines best ideas from v32/v25/v24/v21:
- v25's explore→seek→return→chain_build flow
- v32's network repair and break detection
- v25's fortify system (splitter + ammo-fed gunner)
- Budget-gated conveyor building (never starve)
- Proactive defense: splitter + gunner near core ASAP
- Anti-cheese: detect enemy builders/turrets near core, spawn + heal
- Full 2000 round play
"""

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

DIRS = [d for d in Direction if d != Direction.CENTRE]
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
    }
)
_INFRA = _TRANSPORT | {EntityType.HARVESTER, EntityType.FOUNDRY}

NUM_INITIAL_BUILDERS = 4
MAX_BUILDERS = 12
IDLE_BEFORE_RAID = 50
PATROL_IDLE_LIMIT = 30
TI_WINDOW = 10

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


_DELTA_TO_DIR = {d.delta(): d for d in Direction if d != Direction.CENTRE}


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


def step_conv(ct: Controller, d: Direction, *, skip_ore: bool = False) -> bool:
    """Build conveyors while moving. Budget-gated: only if harvester affordable."""
    if _is_diagonal(d):
        dx, dy = d.delta()
        pair = [_DELTA_TO_DIR[(dx, 0)], _DELTA_TO_DIR[(0, dy)]]
        if random.random() < 0.5:
            pair.reverse()
        return any(step_conv(ct, cd, skip_ore=skip_ore) for cd in pair)
    pos = ct.get_position()
    nxt = pos.add(d)
    if wall(ct, nxt):
        return False
    should_skip = skip_ore and ore_env(ct, nxt)
    if not ore_env(ct, nxt) and not should_skip:
        ti, _ = ct.get_global_resources()
        ti_harv, _ = ct.get_harvester_cost()
        ti_conv, _ = ct.get_conveyor_cost()
        can_afford = ti >= ti_harv + ti_conv
        bid = ct.get_tile_building_id(nxt)
        if (
            can_afford
            and bid is not None
            and ct.get_entity_type(bid) == EntityType.ROAD
            and ct.get_team(bid) == ct.get_team()
        ):
            ct.destroy(nxt)
        if can_afford and ct.can_build_conveyor(nxt, d.opposite()):
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

        if ti < cost:
            return

        my = ct.get_team()

        # ANTI-CHEESE: Spawn defenders toward any enemy near core
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
                if ep.distance_squared(core_pos) <= 49:
                    # Spawn defender every round when under attack
                    self._try_spawn_toward(ct, ep)
                    return

        # Initial builders: wait until we can afford bot + harvester
        if self.spawned < NUM_INITIAL_BUILDERS:
            harv_cost, _ = ct.get_harvester_cost()
            if ti < cost + harv_cost:
                return
            self._try_spawn(ct)
            return

        # After initial builders: spawn for raids when we have surplus
        if rnd < 200 or ti < 300:
            return
        self._try_spawn(ct)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

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
        self.w = 0
        self.h = 0
        self.nav = BugNav()
        self.state = EXPLORE
        self.init_done = False
        self.spoke_dir: Direction | None = None
        self.has_income = False
        self.last_ti = 0
        self.visited_ore: set[tuple[int, int]] = set()
        self.target: Position | None = None
        self.ore_target: Position | None = None
        self.explore_turns = 0
        self.idle_turns = 0
        self.harvesters_built = 0
        self.fortify_count = 0
        self.chain_wait = 0
        self.fortify_target: Position | None = None
        self.fortify_dir: Direction | None = None
        self.fortify_step = 0

    def _setup(self, ct: Controller) -> None:
        pos = ct.get_position()
        rnd = ct.get_current_round()
        my = ct.get_team()
        for eid in ct.get_nearby_entities():
            if ct.get_entity_type(eid) == EntityType.CORE and ct.get_team(eid) == my:
                self.core = ct.get_position(eid)
                break
        if self.core:
            self.w, self.h = ct.get_map_width(), ct.get_map_height()
            self.enemy_core = Position(
                self.w - 1 - self.core.x, self.h - 1 - self.core.y
            )
            self.spoke_dir = toward(self.core, pos)
        if self.spoke_dir is None or self.spoke_dir == Direction.CENTRE:
            self.spoke_dir = random.choice(DIRS)
        if rnd >= 300:
            self.state = RAID
        self.init_done = True

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
        # First exploration: follow spoke direction for straighter chains
        if self.harvesters_built == 0 and self.spoke_dir is not None:
            d = self.spoke_dir
        else:
            d = self._explore_dir(ct, pos)
        dx, dy = d.delta()
        # Keep exploration range moderate to avoid overly long chains
        max_range = max(self.w, self.h) // 4
        dist = random.randint(5, max(6, max_range))
        tx = max(1, min(self.w - 2, pos.x + dx * dist + random.randint(-2, 2)))
        ty = max(1, min(self.h - 2, pos.y + dy * dist + random.randint(-2, 2)))
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
            if et not in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR, EntityType.SPLITTER):
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

    def _find_threats_near_core(
        self, ct: Controller
    ) -> tuple[Position | None, Position | None]:
        """Find enemy turrets and builders near our core.
        Returns (closest_turret, closest_builder)."""
        if self.core is None:
            return None, None
        my = ct.get_team()
        best_turret: Position | None = None
        best_turret_dist = 999999
        best_builder: Position | None = None
        best_builder_dist = 999999
        for eid in ct.get_nearby_entities():
            if ct.get_team(eid) == my:
                continue
            ep = ct.get_position(eid)
            et = ct.get_entity_type(eid)
            if et in (EntityType.GUNNER, EntityType.SENTINEL, EntityType.BREACH):
                d = ep.distance_squared(self.core)
                if d <= 64 and d < best_turret_dist:
                    best_turret_dist = d
                    best_turret = ep
            elif et == EntityType.BUILDER_BOT:
                d = ep.distance_squared(self.core)
                if d <= 49 and d < best_builder_dist:
                    best_builder_dist = d
                    best_builder = ep
        return best_turret, best_builder

    def _find_enemy_conv_near_core(self, ct: Controller) -> Position | None:
        """Find enemy conveyor/transport near our core to destroy."""
        if self.core is None:
            return None
        my = ct.get_team()
        best = None
        best_dist = 999999
        pos = ct.get_position()
        for t in ct.get_nearby_tiles():
            if t.distance_squared(self.core) > 49:
                continue
            bid = ct.get_tile_building_id(t)
            if bid is None or ct.get_team(bid) == my:
                continue
            et = ct.get_entity_type(bid)
            if et in _TRANSPORT:
                d = pos.distance_squared(t)
                if d < best_dist:
                    best_dist = d
                    best = t
        return best

    def _try_heal_core(self, ct: Controller) -> bool:
        if self.core is None:
            return False
        pos = ct.get_position()
        if pos.distance_squared(self.core) <= GameConstants.ACTION_RADIUS_SQ:
            if ct.can_heal(self.core):
                ct.heal(self.core)
                return True
        return False

    def _try_place_gunner_on_network(self, ct: Controller, pos: Position) -> bool:
        """Build a gunner adjacent to our conveyor network, facing toward enemy.
        The gunner will get ammo from the conveyor it's next to."""
        if self.core is None or self.enemy_core is None:
            return False
        my = ct.get_team()
        enemy_dir = toward(self.core, self.enemy_core)
        # Find allied conveyors near core for defensive gunners
        for t in ct.get_nearby_tiles():
            if t.distance_squared(self.core) > 20:
                continue
            bid = ct.get_tile_building_id(t)
            if bid is None or ct.get_team(bid) != my:
                continue
            et = ct.get_entity_type(bid)
            if et not in (EntityType.CONVEYOR, EntityType.SPLITTER):
                continue
            for d in DIRS:
                gp = t.add(d)
                if not ib(ct, gp) or not ct.is_in_vision(gp):
                    continue
                if pos.distance_squared(gp) > GameConstants.ACTION_RADIUS_SQ:
                    continue
                if ct.can_build_gunner(gp, enemy_dir):
                    ct.build_gunner(gp, enemy_dir)
                    return True
        return False

    def _find_core_conv(self, ct: Controller) -> Position | None:
        """Find a conveyor close to our core for early defense fortification."""
        if self.core is None:
            return None
        my = ct.get_team()
        best = None
        best_dist = 999999
        for t in ct.get_nearby_tiles():
            bid = ct.get_tile_building_id(t)
            if bid is None or ct.get_team(bid) != my:
                continue
            if ct.get_entity_type(bid) != EntityType.CONVEYOR:
                continue
            # Must be near core but not ON core
            d = t.distance_squared(self.core)
            if d <= 2 or d > 25:
                continue
            if d < best_dist:
                best_dist = d
                best = t
        return best

    def _find_frontline_conv(self, ct: Controller) -> Position | None:
        """Find a conveyor to fortify (replace with splitter + gunner).
        Looks for a conveyor on our network that's closest to the midpoint
        between cores, but not too close to our core."""
        if self.core is None or self.enemy_core is None:
            return None
        my = ct.get_team()
        mid = Position(
            (self.core.x + self.enemy_core.x) // 2,
            (self.core.y + self.enemy_core.y) // 2,
        )
        best = None
        best_dist = 999999
        for t in ct.get_nearby_tiles():
            bid = ct.get_tile_building_id(t)
            if bid is None or ct.get_team(bid) != my:
                continue
            if ct.get_entity_type(bid) != EntityType.CONVEYOR:
                continue
            if t.distance_squared(self.core) <= 4:
                continue
            d = t.distance_squared(mid)
            if d < best_dist:
                best_dist = d
                best = t
        return best

    # --- Main run ---

    def run(self, ct: Controller) -> None:
        if not self.init_done:
            self._setup(ct)
        if not self.core:
            return

        pos = ct.get_position()
        ti, _ = ct.get_global_resources()

        if not self.has_income and ti > self.last_ti:
            self.has_income = True
        self.last_ti = ti

        # ANTI-CHEESE: defend core - just heal when under attack
        if self.state not in (RAID,):
            enemy_turret, enemy_builder = self._find_threats_near_core(ct)
            if (enemy_turret or enemy_builder) and pos.distance_squared(self.core) <= 64:
                # Heal core - this is the best defense against gunner cheese
                self._try_heal_core(ct)
                return

        # Repair breaks (high priority but not during chain build)
        if self.state not in (RAID, RETURN, CHAIN_BUILD, FORTIFY):
            brk = self._find_break(ct)
            if brk:
                if pos.distance_squared(brk) <= GameConstants.ACTION_RADIUS_SQ:
                    bid = ct.get_tile_building_id(brk)
                    if bid is not None and ct.get_entity_type(bid) in (
                        EntityType.ROAD,
                        EntityType.MARKER,
                    ):
                        ct.destroy(brk)
                    d = repair_dir(ct, brk, self.core)
                    if ct.can_build_conveyor(brk, d):
                        ct.build_conveyor(brk, d)
                        return
                self.nav.go(ct, brk, lambda d: step_road(ct, d))
                return

        # Self-destruct on enemy infrastructure
        if self.state not in (CHAIN_BUILD, RETURN):
            bid = ct.get_tile_building_id(pos)
            if bid is not None and ct.get_team(bid) != ct.get_team():
                et = ct.get_entity_type(bid)
                if et in _INFRA:
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

    # --- States ---

    def _do_explore(self, ct: Controller, pos: Position) -> None:
        adj = self._find_adj_ore(ct, pos)
        if adj:
            self.visited_ore.add((adj.x, adj.y))
            self.ore_target = adj
            # Return to core for clean chain on large maps after first harvester
            if self.harvesters_built > 0 and max(self.w, self.h) > 25:
                self.state = RETURN
            else:
                self.state = CHAIN_BUILD
                self.chain_wait = 0
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
            # Small maps / first harvester: explore with conveyors
            # Large maps after first: roads (return to core for clean chain later)
            use_roads = self.harvesters_built > 0 and max(self.w, self.h) > 25
            if use_roads:
                self.nav.go(ct, self.target, lambda d: step_road(ct, d))
            else:
                self.nav.go(ct, self.target, lambda d: step_conv(ct, d))
            if self.nav.unreachable:
                self.nav.unreachable = False
                self._new_explore_target(ct, ct.get_position())

    def _do_seek_ore(self, ct: Controller, pos: Position) -> None:
        adj = self._find_adj_ore(ct, pos)
        if adj:
            self.visited_ore.add((adj.x, adj.y))
            self.ore_target = adj
            if self.harvesters_built > 0 and max(self.w, self.h) > 25:
                self.state = RETURN
            else:
                self.state = CHAIN_BUILD
                self.chain_wait = 0
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

        use_roads = self.harvesters_built > 0 and max(self.w, self.h) > 25
        if use_roads:
            self.nav.go(ct, self.target, lambda d: step_road(ct, d))
        else:
            self.nav.go(ct, self.target, lambda d: step_conv(ct, d))
        if self.nav.unreachable:
            self.nav.unreachable = False
            self.state = EXPLORE
            self._new_explore_target(ct, ct.get_position())

    def _do_return(self, ct: Controller, pos: Position) -> None:
        if self.core is None:
            self.state = EXPLORE
            return
        if pos.distance_squared(self.core) <= 2:
            self.state = CHAIN_BUILD
            self.nav.reset()
            self.chain_wait = 0
            return
        self.nav.go(ct, self.core, lambda d: step_walk(ct, d))

    def _has_adjacent_conveyor(self, ct: Controller, ore: Position) -> bool:
        """Check if ore has a cardinal-adjacent allied conveyor/splitter."""
        my = ct.get_team()
        for d in CARDINALS:
            adj = ore.add(d)
            if not ib(ct, adj):
                continue
            bid = ct.get_tile_building_id(adj)
            if bid is not None and ct.get_team(bid) == my:
                et = ct.get_entity_type(bid)
                if et in (
                    EntityType.CONVEYOR,
                    EntityType.ARMOURED_CONVEYOR,
                    EntityType.SPLITTER,
                ):
                    return True
        return False

    def _do_chain_build(self, ct: Controller, pos: Position) -> None:
        if not self.ore_target:
            self.state = EXPLORE
            return

        # Only place harvester if it has a connected conveyor adjacent
        if (
            ct.can_build_harvester(self.ore_target)
            and self._has_adjacent_conveyor(ct, self.ore_target)
        ):
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

        # Budget gate
        ti, _ = ct.get_global_resources()
        ti_harv, _ = ct.get_harvester_cost()
        ti_conv, _ = ct.get_conveyor_cost()
        if ti < ti_harv + ti_conv:
            self.chain_wait += 1
            if self.chain_wait > 80:
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

        ore = self._find_visible_ore(ct, pos)
        if ore:
            self.visited_ore.add((ore.x, ore.y))
            self.ore_target = ore
            if self.harvesters_built > 0 and max(self.w, self.h) > 25:
                self.state = RETURN
            else:
                self.state = CHAIN_BUILD
                self.chain_wait = 0
            self.idle_turns = 0
            self.nav.reset()
            return

        # Build gunner adjacent to conveyor for defense
        if self.fortify_count < 3 and self.harvesters_built >= 1:
            ti, _ = ct.get_global_resources()
            gun_cost, _ = ct.get_gunner_cost()
            if ti > gun_cost + 20:
                built = self._try_place_gunner_on_network(ct, pos)
                if built:
                    self.fortify_count += 1
                    return

        self.idle_turns += 1
        if self.has_income and self.idle_turns >= IDLE_BEFORE_RAID:
            self.state = RAID
            self.nav.reset()
            return

        if self.idle_turns > PATROL_IDLE_LIMIT:
            self.state = PATROL
            self._new_explore_target(ct, ct.get_position())
            return

        if self.core and pos.distance_squared(self.core) > 4:
            self.nav.go(ct, self.core, lambda d: step_walk(ct, d))

    def _do_fortify(self, ct: Controller, pos: Position) -> None:
        """Replace a conveyor with a splitter, then build gunner adjacent.
        The splitter continues the resource chain while the gunner
        gets ammo from the splitter's side outputs."""
        if self.core is None or self.enemy_core is None:
            self.state = MAINTAIN
            self.idle_turns = 0
            return
        if not self.fortify_target:
            self.state = MAINTAIN
            self.idle_turns = 0
            return

        if self.fortify_step == 1:
            # Move to conveyor to destroy it
            if (
                pos.distance_squared(self.fortify_target)
                > GameConstants.ACTION_RADIUS_SQ
            ):
                self.nav.go(ct, self.fortify_target, lambda d: step_walk(ct, d))
                return
            bid = ct.get_tile_building_id(self.fortify_target)
            if bid is None or ct.get_entity_type(bid) != EntityType.CONVEYOR:
                self.fortify_target = None
                self.state = MAINTAIN
                self.idle_turns = 0
                return
            self.fortify_dir = ct.get_direction(bid)
            ct.destroy(self.fortify_target)
            self.fortify_step = 2
            return

        if self.fortify_step == 2:
            # Build splitter in same direction
            if self.fortify_dir is None:
                self.state = MAINTAIN
                self.idle_turns = 0
                return
            if ct.can_build_splitter(self.fortify_target, self.fortify_dir):
                ct.build_splitter(self.fortify_target, self.fortify_dir)
                self.fortify_step = 3
            else:
                self.fortify_target = None
                self.state = MAINTAIN
                self.idle_turns = 0
            return

        if self.fortify_step == 3:
            # Build gunner adjacent to splitter, facing enemy core
            # CRITICAL: gunner must NOT face toward the splitter (ammo source)
            enemy_dir = toward(self.fortify_target, self.enemy_core)
            for try_d in [
                self.fortify_dir.rotate_left().rotate_left(),
                self.fortify_dir.rotate_right().rotate_right(),
                self.fortify_dir.rotate_left(),
                self.fortify_dir.rotate_right(),
            ]:
                gun_pos = self.fortify_target.add(try_d)
                if not ib(ct, gun_pos) or not ct.is_in_vision(gun_pos) or wall(ct, gun_pos):
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
                    self.fortify_count += 1
                    self.state = MAINTAIN
                    self.idle_turns = 0
                    return

            # Couldn't place gunner, give up
            self.fortify_target = None
            self.fortify_step = 0
            self.fortify_count += 1
            self.state = MAINTAIN
            self.idle_turns = 0

    def _do_patrol(self, ct: Controller, pos: Position) -> None:
        adj = self._find_adj_ore(ct, pos)
        if adj:
            self.visited_ore.add((adj.x, adj.y))
            self.ore_target = adj
            if self.harvesters_built > 0 and max(self.w, self.h) > 25:
                self.state = RETURN
            else:
                self.state = CHAIN_BUILD
                self.chain_wait = 0
            self.idle_turns = 0
            self.nav.reset()
            return

        ore = self._find_visible_ore(ct, pos)
        if ore:
            self.state = SEEK_ORE
            self.target = ore
            self.idle_turns = 0
            self.nav.reset()
            return

        brk = self._find_break(ct)
        if brk:
            self.state = MAINTAIN
            self.idle_turns = 0
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

    def _do_raid(self, ct: Controller, pos: Position) -> None:
        if self.core is None or self.enemy_core is None:
            return
        my = ct.get_team()

        bid = ct.get_tile_building_id(pos)
        if bid is not None and ct.get_team(bid) != my:
            et = ct.get_entity_type(bid)
            if et in _INFRA:
                ct.self_destruct()
                return

        past_midpoint = pos.distance_squared(self.enemy_core) < pos.distance_squared(
            self.core
        )
        if past_midpoint:
            best = None
            best_dist = 999999
            for eid in ct.get_nearby_entities():
                if ct.get_team(eid) == my:
                    continue
                et = ct.get_entity_type(eid)
                if et in (EntityType.HARVESTER, EntityType.FOUNDRY):
                    ep = ct.get_position(eid)
                    self.nav.go(ct, ep, lambda d: step_raid(ct, d))
                    return
                if et not in _TRANSPORT:
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


# ---------------------------------------------------------------------------
# Turret
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
