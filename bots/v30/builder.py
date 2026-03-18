import random
from dataclasses import dataclass, field

from bugnav import BugNav
from cambc import Controller, EntityType, GameConstants, Position
from comms import MarkerReader, MarkerWriter
from marker import BreakAlert, PressureSummary, Threat, Urgency
from network import NetworkBelief
from params import (
    DEFENSE_MIN_HARVESTERS,
    PATROL_IDLE_LIMIT,
    REPULSION_JITTER,
)
from util import DIRS, ore_env, repair_dir, step_conv, step_road

_DESTRUCTIBLE = frozenset(
    {
        EntityType.CONVEYOR,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.SPLITTER,
        EntityType.HARVESTER,
        EntityType.FOUNDRY,
        EntityType.BRIDGE,
    },
)


@dataclass
class ExploreConv:
    nav: BugNav = field(default_factory=BugNav)
    target: Position | None = None


@dataclass
class Patrol:
    nav: BugNav = field(default_factory=BugNav)
    target: Position | None = None
    idle_turns: int = 0


State = ExploreConv | Patrol


class BuilderAgent:
    def __init__(self) -> None:
        self.core: Position | None = None
        self.enemy_core: Position | None = None
        self.w = 0
        self.h = 0
        self.net = NetworkBelief()
        self.state: State = ExploreConv()
        self.reader = MarkerReader()
        self.writer = MarkerWriter()
        self.harvesters_built = 0

    def _setup(self, ct: Controller) -> None:
        my = ct.get_team()
        self.w, self.h = ct.get_map_width(), ct.get_map_height()
        for eid in ct.get_nearby_entities():
            if ct.get_entity_type(eid) == EntityType.CORE and ct.get_team(eid) == my:
                self.core = ct.get_position(eid)
                break
        if self.core is not None:
            self.enemy_core = Position(
                self.w - 1 - self.core.x,
                self.h - 1 - self.core.y,
            )

    def _find_ore(self, ct: Controller) -> Position | None:
        pos = ct.get_position()
        best: Position | None = None
        best_dist = 999999
        for t in ct.get_nearby_tiles():
            if not ore_env(ct, t) or ct.get_tile_building_id(t) is not None:
                continue
            if self.reader.is_ore_claimed(t):
                continue
            d = pos.distance_squared(t)
            if d < best_dist:
                best_dist = d
                best = t
        return best

    def _find_enemy_near_core(self, ct: Controller) -> Position | None:
        assert self.core is not None
        my = ct.get_team()
        for eid in ct.get_nearby_entities():
            if ct.get_team(eid) == my:
                continue
            ep = ct.get_position(eid)
            if ep.distance_squared(self.core) <= 36:
                return ep
        return None

    def _try_build_gunner(self, ct: Controller, near: Position) -> bool:
        assert self.enemy_core is not None
        facing = near.direction_to(self.enemy_core)
        for d in DIRS:
            gp = near.add(d)
            for f in (facing, facing.rotate_left(), facing.rotate_right()):
                if ct.can_build_gunner(gp, f):
                    ct.build_gunner(gp, f)
                    return True
        return False

    def _pick_chain_target(self) -> Position | None:
        assert self.core is not None
        farthest: Position | None = None
        farthest_dist = 0
        for p in self.net.connected_tiles():
            d = self.core.distance_squared(p)
            if d > farthest_dist:
                farthest_dist = d
                farthest = p
        return farthest

    def _break_from_comms(self, pos: Position) -> Position | None:
        best: Position | None = None
        best_dist = 999999
        for _, b in self.reader.breaks:
            p = Position(b.break_x, b.break_y)
            d = pos.distance_squared(p)
            if d < best_dist:
                best_dist = d
                best = p
        return best

    def _pick_explore_target(self, ct: Controller) -> Position:
        pos = ct.get_position()
        my = ct.get_team()
        fx, fy = 0.0, 0.0
        for eid in ct.get_nearby_entities():
            if (
                ct.get_team(eid) != my
                or ct.get_entity_type(eid) != EntityType.BUILDER_BOT
            ):
                continue
            ep = ct.get_position(eid)
            dx, dy = pos.x - ep.x, pos.y - ep.y
            if dx == 0 and dy == 0:
                continue
            dist_sq = dx * dx + dy * dy
            fx += dx / dist_sq
            fy += dy / dist_sq
        fx += random.uniform(-REPULSION_JITTER, REPULSION_JITTER)
        fy += random.uniform(-REPULSION_JITTER, REPULSION_JITTER)
        if fx == 0.0 and fy == 0.0:
            d = random.choice(DIRS)
            fx, fy = d.delta()
        scale = max(self.w, self.h) // 2
        tx = max(0, min(self.w - 1, round(pos.x + fx * scale)))
        ty = max(0, min(self.h - 1, round(pos.y + fy * scale)))
        return Position(tx, ty)

    def _initial_target(self, ct: Controller) -> Position:
        assert self.core is not None
        pos = ct.get_position()
        d = self.core.direction_to(pos)
        dx, dy = d.delta()
        return Position(
            max(0, min(self.w - 1, pos.x + dx * self.w)),
            max(0, min(self.h - 1, pos.y + dy * self.h)),
        )

    def _retarget(self, s: ExploreConv | Patrol, pos: Position) -> bool:
        if s.target is None:
            return True
        if s.nav.unreachable:
            s.nav.unreachable = False
            return True
        return pos.x == s.target.x and pos.y == s.target.y

    def _propose_markers(self, ct: Controller) -> None:
        pos = ct.get_position()
        rnd = ct.get_current_round()
        my = ct.get_team()

        for eid in ct.get_nearby_entities():
            if ct.get_team(eid) == my:
                continue
            ep = ct.get_position(eid)
            et = ct.get_entity_type(eid)
            comp = 0
            if et == EntityType.BUILDER_BOT:
                comp = 0b1000
            elif et == EntityType.GUNNER:
                comp = 0b0100
            elif et == EntityType.SENTINEL:
                comp = 0b0010
            elif et == EntityType.BREACH:
                comp = 0b0001
            self.writer.propose(
                pos,
                Threat(
                    enemy_x=ep.x,
                    enemy_y=ep.y,
                    enemy_composition=comp,
                    enemy_count=1,
                    freshness=rnd % 64,
                    urgency=Urgency.HIGH,
                ),
                priority=100,
            )
            break

        assert self.core is not None
        brk = self.net.find_break(ct, self.core)
        if brk:
            already_alerted = any(
                b.break_x == brk.x and b.break_y == brk.y for _, b in self.reader.breaks
            )
            if not already_alerted:
                self.writer.propose(
                    pos,
                    BreakAlert(
                        break_x=brk.x,
                        break_y=brk.y,
                        repair_direction=0,
                        chain_importance=0,
                        freshness=rnd % 64,
                        break_type=0,
                    ),
                    priority=80,
                )

        congested = self.net.congested_tiles()
        if congested:
            t = congested[0]
            info = self.net.get(t)
            self.writer.propose(
                pos,
                PressureSummary(
                    pos_x=t.x,
                    pos_y=t.y,
                    pressure_level=min(15, info.upstream_harvesters if info else 0),
                    upstream_harvesters=info.upstream_harvesters if info else 0,
                    freshness=rnd % 64,
                    chain_direction=0,
                ),
                priority=20,
            )

    def run(self, ct: Controller) -> None:
        if self.core is None:
            self._setup(ct)
        if self.core is None:
            return

        self.net.update(ct, self.core)
        self.reader.scan(ct)

        pos = ct.get_position()
        my = ct.get_team()

        enemy = self._find_enemy_near_core(ct)
        if enemy and pos.distance_squared(self.core) <= 36:
            if pos.distance_squared(enemy) <= GameConstants.ACTION_RADIUS_SQ:
                bid = ct.get_tile_building_id(enemy)
                if bid is not None and ct.get_team(bid) != my:
                    ct.heal(self.core)
                    return
            s = self.state
            if isinstance(s, (ExploreConv, Patrol)):
                s.nav.go(ct, enemy, lambda d: step_road(ct, d))
                self._propose_markers(ct)
                self.writer.flush(ct)
                return

        match self.state:
            case ExploreConv() as s:
                ore = self._find_ore(ct)
                if ore and pos.distance_squared(ore) <= GameConstants.ACTION_RADIUS_SQ:
                    if ct.can_build_harvester(ore):
                        ct.build_harvester(ore)
                        self.harvesters_built += 1
                        if self.harvesters_built >= DEFENSE_MIN_HARVESTERS:
                            self._try_build_gunner(ct, self.core)
                    return
                if ore:
                    s.target = ore
                    s.nav.reset()
                elif self._retarget(s, pos):
                    if s.target is None:
                        s.target = self._initial_target(ct)
                    else:
                        s.target = self._pick_explore_target(ct)
                    s.nav.reset()
                if s.target is not None:
                    ti, _ = ct.get_global_resources()
                    conv_cost, _ = ct.get_conveyor_cost()
                    reserve = conv_cost
                    if ore and pos.distance_squared(ore) <= 4:
                        ti_cost, _ = ct.get_harvester_cost()
                        reserve += ti_cost
                    if ti < reserve:
                        return
                    s.nav.go(ct, s.target, lambda d: step_conv(ct, d))

            case Patrol() as s:
                brk = self.net.find_break(ct, self.core)
                if brk and pos.distance_squared(brk) <= GameConstants.ACTION_RADIUS_SQ:
                    d = repair_dir(ct, brk, self.core)
                    if ct.can_build_conveyor(brk, d):
                        ct.build_conveyor(brk, d)
                    s.idle_turns = 0
                    return

                if brk:
                    s.target = brk
                    s.nav.reset()
                    s.idle_turns = 0
                    s.nav.go(ct, s.target, lambda d: step_road(ct, d))
                    self._propose_markers(ct)
                    self.writer.flush(ct)
                    return

                brk_from_comms = self._break_from_comms(pos)
                if brk_from_comms:
                    s.target = brk_from_comms
                    s.nav.reset()
                    s.idle_turns = 0
                    s.nav.go(ct, s.target, lambda d: step_road(ct, d))
                    self._propose_markers(ct)
                    self.writer.flush(ct)
                    return

                ore = self._find_ore(ct)
                if ore:
                    anchor = (
                        self.net.nearest_connected(pos, max_upstream=4) or self.core
                    )
                    assert anchor is not None
                    self.state = WalkToAnchor(ore=ore, anchor=anchor)
                    s.idle_turns = 0
                else:
                    s.idle_turns += 1
                    if s.idle_turns >= PATROL_IDLE_LIMIT:
                        self.state = ExploreConv()
                    elif self._retarget(s, pos):
                        chain_t = self._pick_chain_target()
                        if chain_t:
                            s.target = chain_t
                        else:
                            s.target = self._pick_explore_target(ct)
                        s.nav.reset()
                if isinstance(self.state, Patrol):
                    if s.target is not None:
                        s.nav.go(ct, s.target, lambda d: step_road(ct, d))

        self._propose_markers(ct)
        self.writer.flush(ct)
