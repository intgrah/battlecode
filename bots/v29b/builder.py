import math
import random
from dataclasses import dataclass, field

from bugnav import BugNav
from cambc import Controller, EntityType, GameConstants, Position
from comms import MarkerReader, MarkerWriter
from marker import BreakAlert, ClaimState, OreClaim, PressureSummary, Threat, Urgency
from params import (
    DEFENSE_MIN_HARVESTERS,
    PATROL_IDLE_LIMIT,
    RAID_MIN_HARVESTERS,
    REPULSION_JITTER,
)
from util import DIRS, ore_env, step_conv, step_patrol, step_raid

_TRANSPORT = frozenset(
    {
        EntityType.CONVEYOR,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.SPLITTER,
        EntityType.BRIDGE,
    },
)

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
class ExploreRoad:
    nav: BugNav = field(default_factory=BugNav)
    target: Position | None = None


@dataclass
class WalkToAnchor:
    ore: Position
    anchor: Position
    nav: BugNav = field(default_factory=BugNav)


@dataclass
class BuildChain:
    ore: Position
    nav: BugNav = field(default_factory=BugNav)
    wait_turns: int = 0


@dataclass
class Patrol:
    nav: BugNav = field(default_factory=BugNav)
    target: Position | None = None
    idle_turns: int = 0


@dataclass
class Raid:
    nav: BugNav = field(default_factory=BugNav)


State = ExploreRoad | WalkToAnchor | BuildChain | Patrol | Raid


class BuilderAgent:
    def __init__(self) -> None:
        self.core: Position | None = None
        self.enemy_core: Position | None = None
        self.w = 0
        self.h = 0
        self.connected: dict[Position, bool] = {}
        self.state: State = ExploreRoad()
        self.reader = MarkerReader()
        self.writer = MarkerWriter()
        self.harvesters_seen = 0

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

    def _update_connected(self, ct: Controller) -> None:
        assert self.core is not None
        my = ct.get_team()
        cx, cy = self.core.x, self.core.y
        for t in ct.get_nearby_tiles():
            bid = ct.get_tile_building_id(t)
            if bid is None or ct.get_team(bid) != my:
                self.connected.pop(t, None)
                continue
            et = ct.get_entity_type(bid)
            if et not in _TRANSPORT:
                self.connected.pop(t, None)
                continue
            x, y = t.x, t.y
            visited: list[Position] = []
            seen: set[tuple[int, int]] = set()
            result: bool | None = None
            while (x, y) not in seen:
                seen.add((x, y))
                p = Position(x, y)
                visited.append(p)
                if abs(x - cx) <= 1 and abs(y - cy) <= 1:
                    result = True
                    break
                if not ct.is_in_vision(p):
                    break
                b = ct.get_tile_building_id(p)
                if b is None or ct.get_team(b) != my:
                    result = False
                    break
                bt = ct.get_entity_type(b)
                if bt not in _TRANSPORT:
                    result = False
                    break
                dx, dy = ct.get_direction(b).delta()
                x, y = x + dx, y + dy
            if result is not None:
                for v in visited:
                    self.connected[v] = result

    def _count_connected_harvesters(self, ct: Controller) -> int:
        assert self.core is not None
        my = ct.get_team()
        count = 0
        for t in ct.get_nearby_tiles():
            bid = ct.get_tile_building_id(t)
            if bid is None or ct.get_team(bid) != my:
                continue
            if ct.get_entity_type(bid) != EntityType.HARVESTER:
                continue
            for d in DIRS:
                adj = t.add(d)
                if self.connected.get(adj, False):
                    count += 1
                    break
        return count

    def _measure_pressure(self, ct: Controller) -> dict[Position, bool]:
        my = ct.get_team()
        pressure: dict[Position, bool] = {}
        for t in ct.get_nearby_tiles():
            bid = ct.get_tile_building_id(t)
            if bid is None or ct.get_team(bid) != my:
                continue
            if ct.get_entity_type(bid) not in _TRANSPORT:
                continue
            pressure[t] = ct.get_stored_resource(bid) is not None
        return pressure

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

    def _ore_in_vision(self, ct: Controller) -> bool:
        for t in ct.get_nearby_tiles():
            if ore_env(ct, t) and ct.get_tile_building_id(t) is None:
                return True
        return False

    def _nearest_connected(
        self,
        pos: Position,
        pressure: dict[Position, bool],
    ) -> Position | None:
        best: Position | None = None
        best_score = 999999.0
        for p, is_connected in self.connected.items():
            if not is_connected:
                continue
            dist = pos.distance_squared(p)
            full = pressure.get(p, False)
            score = dist + (100.0 if full else 0.0)
            if score < best_score:
                best_score = score
                best = p
        return best

    def _best_capacity_anchor(self, pos: Position) -> Position | None:
        best: Position | None = None
        best_score = 999999.0
        for _, ps in self.reader.pressure:
            if ps.spare_capacity < 2:
                continue
            ap = Position(ps.pos_x, ps.pos_y)
            dist = pos.distance_squared(ap)
            score = dist - ps.spare_capacity * 10
            if score < best_score:
                best_score = score
                best = ap
        return best

    def _find_break(self, ct: Controller) -> Position | None:
        assert self.core is not None
        my = ct.get_team()
        cx, cy = self.core.x, self.core.y
        for t in ct.get_nearby_tiles():
            bid = ct.get_tile_building_id(t)
            if bid is None or ct.get_team(bid) != my:
                continue
            et = ct.get_entity_type(bid)
            if et not in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR):
                continue
            dx, dy = ct.get_direction(bid).delta()
            out = Position(t.x + dx, t.y + dy)
            if not ct.is_in_vision(out):
                continue
            if ct.get_tile_building_id(out) is not None:
                continue
            if abs(out.x - cx) <= 1 and abs(out.y - cy) <= 1:
                continue
            return out
        return None

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

    def _pick_chain_walk_target(self, ct: Controller) -> Position | None:
        pos = ct.get_position()
        best: Position | None = None
        best_dist = 0
        for p, is_connected in self.connected.items():
            if not is_connected:
                continue
            d = pos.distance_squared(p)
            if d > best_dist and d <= 20:
                best_dist = d
                best = p
        if best is None:
            for p, is_connected in self.connected.items():
                if not is_connected:
                    continue
                d = pos.distance_squared(p)
                if d > best_dist:
                    best_dist = d
                    best = p
        return best

    def _retarget(self, s: ExploreRoad | Patrol, pos: Position) -> bool:
        if s.target is None:
            return True
        if s.nav.unreachable:
            s.nav.unreachable = False
            return True
        return pos.x == s.target.x and pos.y == s.target.y

    def _try_place_gunner(self, ct: Controller) -> bool:
        assert self.core is not None
        assert self.enemy_core is not None
        ct.get_team()
        pos = ct.get_position()
        enemy_dir = pos.direction_to(self.enemy_core)
        for t in ct.get_nearby_tiles():
            if pos.distance_squared(t) > GameConstants.ACTION_RADIUS_SQ:
                continue
            if ct.get_tile_building_id(t) is not None:
                continue
            for d in DIRS:
                adj = t.add(d)
                if not self.connected.get(adj, False):
                    continue
                adj_bid = ct.get_tile_building_id(adj)
                if adj_bid is None:
                    continue
                if ct.get_entity_type(adj_bid) not in _TRANSPORT:
                    continue
                if ct.can_build_gunner(t, enemy_dir):
                    ct.build_gunner(t, enemy_dir)
                    return True
        return False

    def _propose_markers(self, ct: Controller, pressure: dict[Position, bool]) -> None:
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

        brk = self._find_break(ct)
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

        total = len(pressure)
        if total > 0:
            full_count = sum(1 for v in pressure.values() if v)
            empty_count = total - full_count
            spare = min(15, empty_count // max(1, total // 4))
            assert self.core is not None
            dist_to_core = min(15, math.isqrt(pos.distance_squared(self.core)))
            self.writer.propose(
                pos,
                PressureSummary(
                    pos_x=pos.x,
                    pos_y=pos.y,
                    spare_capacity=spare,
                    dist_to_core=dist_to_core,
                    freshness=rnd % 64,
                    resource_type=0,
                ),
                priority=20,
            )

    def run(self, ct: Controller) -> None:
        if self.core is None:
            self._setup(ct)
        if self.core is None:
            return

        self._update_connected(ct)
        pressure = self._measure_pressure(ct)
        self.reader.scan(ct)

        pos = ct.get_position()
        my = ct.get_team()

        local_harv = self._count_connected_harvesters(ct)
        self.harvesters_seen = max(self.harvesters_seen, local_harv)

        bid = ct.get_tile_building_id(pos)
        if (
            bid is not None
            and ct.get_team(bid) != my
            and ct.get_entity_type(bid) in _DESTRUCTIBLE
        ):
            ct.self_destruct()
            return

        match self.state:
            case ExploreRoad() as s:
                ore = self._find_ore(ct)
                if ore:
                    anchor = (
                        self._best_capacity_anchor(pos)
                        or self._nearest_connected(pos, pressure)
                        or self.core
                    )
                    assert anchor is not None
                    rnd = ct.get_current_round()
                    self.writer.propose(
                        pos,
                        OreClaim(
                            ore_x=ore.x,
                            ore_y=ore.y,
                            state=ClaimState.CLAIMED,
                            claimer_hash=ct.get_id() % 64,
                            freshness=rnd % 64,
                            ore_type=0,
                        ),
                        priority=60,
                    )
                    self.state = WalkToAnchor(ore=ore, anchor=anchor)
                elif self._retarget(s, pos):
                    if s.target is None:
                        s.target = self._initial_target(ct)
                    else:
                        s.target = self._pick_explore_target(ct)
                    s.nav.reset()
                if isinstance(self.state, ExploreRoad):
                    assert s.target is not None
                    s.nav.go(ct, s.target, lambda d: step_patrol(ct, d))

            case WalkToAnchor() as s:
                if pos.distance_squared(s.anchor) <= GameConstants.ACTION_RADIUS_SQ:
                    d = pos.direction_to(s.anchor)
                    if ct.can_build_conveyor(pos, d):
                        ct.build_conveyor(pos, d)
                    self.state = BuildChain(ore=s.ore)
                else:
                    s.nav.go(ct, s.anchor, lambda d: step_patrol(ct, d))

            case BuildChain() as s:
                if pos.distance_squared(s.ore) == 1:
                    if ct.can_build_harvester(s.ore):
                        ct.build_harvester(s.ore)
                        if self.harvesters_seen >= DEFENSE_MIN_HARVESTERS:
                            self._try_place_gunner(ct)
                        self.state = Patrol()
                    else:
                        s.wait_turns += 1
                        if s.wait_turns > 60:
                            self.state = Patrol()
                    return
                ti, _ = ct.get_global_resources()
                conv_cost, _ = ct.get_conveyor_cost()
                if ti < conv_cost * 2:
                    s.wait_turns += 1
                    if s.wait_turns > 60:
                        self.state = Patrol()
                    return
                s.wait_turns = 0
                s.nav.go(ct, s.ore, lambda d: step_conv(ct, d))

            case Patrol() as s:
                brk = self._find_break(ct)
                if brk and pos.distance_squared(brk) <= GameConstants.ACTION_RADIUS_SQ:
                    from util import repair_dir

                    assert self.core is not None
                    d = repair_dir(ct, brk, self.core)
                    if ct.can_build_conveyor(brk, d):
                        ct.build_conveyor(brk, d)
                    s.idle_turns = 0
                    self._propose_markers(ct, pressure)
                    self.writer.flush(ct)
                    return

                ore = self._find_ore(ct)
                if ore:
                    ti, _ = ct.get_global_resources()
                    ti_cost, _ = ct.get_harvester_cost()
                    conv_cost, _ = ct.get_conveyor_cost()
                    ore_visible = self._ore_in_vision(ct)
                    reserve = (ti_cost + conv_cost) if ore_visible else conv_cost
                    if ti >= reserve:
                        anchor = (
                            self._best_capacity_anchor(pos)
                            or self._nearest_connected(pos, pressure)
                            or self.core
                        )
                        assert anchor is not None
                        self.state = WalkToAnchor(ore=ore, anchor=anchor)
                        s.idle_turns = 0
                    else:
                        s.idle_turns += 1
                else:
                    s.idle_turns += 1

                rnd = ct.get_current_round()
                if (
                    isinstance(self.state, Patrol)
                    and self.harvesters_seen >= RAID_MIN_HARVESTERS
                    and rnd > 500
                    and s.idle_turns >= PATROL_IDLE_LIMIT
                ):
                    self.state = Raid()
                elif (
                    isinstance(self.state, Patrol) and s.idle_turns >= PATROL_IDLE_LIMIT
                ):
                    self.state = ExploreRoad()
                elif isinstance(self.state, Patrol):
                    if self._retarget(s, pos):
                        chain_target = self._pick_chain_walk_target(ct)
                        if chain_target is not None and s.idle_turns > 5:
                            s.target = chain_target
                        else:
                            s.target = self._pick_explore_target(ct)
                        s.nav.reset()
                    if s.target is not None:
                        s.nav.go(ct, s.target, lambda d: step_patrol(ct, d))

            case Raid() as s:
                assert self.enemy_core is not None
                enemy_bid = ct.get_tile_building_id(pos)
                if enemy_bid is not None and ct.get_team(enemy_bid) != my:
                    ct.self_destruct()
                    return
                s.nav.go(ct, self.enemy_core, lambda d: step_raid(ct, d))

        self._propose_markers(ct, pressure)
        self.writer.flush(ct)
