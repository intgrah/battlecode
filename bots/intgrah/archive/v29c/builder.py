import random
from dataclasses import dataclass, field

from bugnav import BugNav
from cambc import Controller, EntityType, Environment, GameConstants, Position
from comms import MarkerReader, MarkerWriter
from marker import (
    FLAG_BREAK_DETECTED,
    FLAG_CONGESTED,
    BreakAlert,
    ClaimState,
    OreClaim,
    PressureSummary,
    Threat,
    Urgency,
)
from params import (
    PRESSURE_HIGH,
    RAID_EXPLORE_TIMEOUT,
    RAID_LATE_EXPLORE_ROUND,
    RAID_ROUND_THRESHOLD,
    REPULSION_JITTER,
)
from util import (
    DIRS,
    SPOKES,
    ore_env,
    repair_dir,
    step_conv,
    step_raid,
    step_road,
    step_walk,
)

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
    turns_without_ore: int = 0


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
        self.harvesters_built = 0
        self.spawn_round = 0

    def _setup(self, ct: Controller) -> None:
        my = ct.get_team()
        self.w, self.h = ct.get_map_width(), ct.get_map_height()
        self.spawn_round = ct.get_current_round()
        for eid in ct.get_nearby_entities():
            if ct.get_entity_type(eid) == EntityType.CORE and ct.get_team(eid) == my:
                self.core = ct.get_position(eid)
                break
        if self.core is not None:
            self.enemy_core = Position(
                self.w - 1 - self.core.x,
                self.h - 1 - self.core.y,
            )
        if self.spawn_round >= RAID_ROUND_THRESHOLD:
            self.state = Raid()

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

    def _retarget(self, s: ExploreRoad | Patrol, pos: Position) -> bool:
        if s.target is None:
            return True
        if s.nav.unreachable:
            s.nav.unreachable = False
            return True
        return pos.x == s.target.x and pos.y == s.target.y

    def _pick_patrol_target(self, ct: Controller) -> Position | None:
        assert self.core is not None
        pos = ct.get_position()

        brk_alerts = self.reader.breaks
        if brk_alerts:
            best = None
            best_dist = 999999
            for _, b in brk_alerts:
                bp = Position(b.break_x, b.break_y)
                d = pos.distance_squared(bp)
                if d < best_dist:
                    best_dist = d
                    best = bp
            if best is not None:
                return best

        chain_positions = [p for p, c in self.connected.items() if c]
        if chain_positions:
            return max(chain_positions, key=lambda p: p.distance_squared(self.core))

        return None

    def _should_raid(self, ct: Controller, idle_turns: int = 0) -> bool:
        rnd = ct.get_current_round()
        if rnd < RAID_ROUND_THRESHOLD:
            return False
        ore = self._find_ore(ct)
        if ore is not None:
            return False
        if self.harvesters_built >= 2 and idle_turns > 30:
            return True
        return idle_turns > 100

    def _find_enemy_infra(self, ct: Controller) -> Position | None:
        my = ct.get_team()
        pos = ct.get_position()
        best: Position | None = None
        best_dist = 999999
        for eid in ct.get_nearby_entities():
            if ct.get_team(eid) == my:
                continue
            et = ct.get_entity_type(eid)
            if et in _DESTRUCTIBLE:
                ep = ct.get_position(eid)
                d = pos.distance_squared(ep)
                if d < best_dist:
                    best_dist = d
                    best = ep
        return best

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

        full_count = sum(1 for v in pressure.values() if v)
        total = len(pressure)
        if total > 0:
            assert self.core is not None
            core_dir_idx = 0
            core_d = pos.direction_to(self.core)
            for i, s in enumerate(SPOKES):
                if s == core_d:
                    core_dir_idx = i
                    break
            flags = 0
            has_break = brk is not None
            if has_break:
                flags |= FLAG_BREAK_DETECTED
            if total > 0 and full_count / total > PRESSURE_HIGH:
                flags |= FLAG_CONGESTED
            self.writer.propose(
                pos,
                PressureSummary(
                    pos_x=pos.x,
                    pos_y=pos.y,
                    pressure_level=min(15, full_count),
                    core_direction=core_dir_idx,
                    freshness=rnd % 64,
                    flags=flags,
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
        rnd = ct.get_current_round()

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
                    s.turns_without_ore = 0
                    anchor = self._nearest_connected(pos, pressure) or self.core
                    assert anchor is not None
                    self.writer.propose(
                        pos,
                        OreClaim(
                            ore_x=ore.x,
                            ore_y=ore.y,
                            state=ClaimState.CLAIMED,
                            claimer_hash=ct.get_id() % 64,
                            freshness=rnd % 64,
                            ore_type=1
                            if ct.get_tile_env(ore) == Environment.ORE_AXIONITE
                            else 0,
                        ),
                        priority=60,
                    )
                    self.state = WalkToAnchor(ore=ore, anchor=anchor)
                else:
                    s.turns_without_ore += 1
                    if (
                        rnd > RAID_LATE_EXPLORE_ROUND
                        and s.turns_without_ore > RAID_EXPLORE_TIMEOUT
                    ):
                        self.state = Raid()
                    elif self._retarget(s, pos):
                        if s.target is None:
                            s.target = self._initial_target(ct)
                        else:
                            s.target = self._pick_explore_target(ct)
                        s.nav.reset()
                if isinstance(self.state, ExploreRoad):
                    assert s.target is not None
                    s.nav.go(ct, s.target, lambda d: step_road(ct, d))

            case WalkToAnchor() as s:
                if pos.distance_squared(s.anchor) <= GameConstants.ACTION_RADIUS_SQ:
                    d = pos.direction_to(s.anchor)
                    if ct.can_build_conveyor(pos, d):
                        ct.build_conveyor(pos, d)
                    self.state = BuildChain(ore=s.ore)
                else:
                    s.nav.go(ct, s.anchor, lambda d: step_road(ct, d))

            case BuildChain() as s:
                if pos.distance_squared(s.ore) == 1:
                    if ct.can_build_harvester(s.ore):
                        ct.build_harvester(s.ore)
                        self.harvesters_built += 1
                        self.state = Patrol()
                        return
                    s.wait_turns += 1
                    if s.wait_turns > 100:
                        self.state = Patrol()
                    return
                ti, _ = ct.get_global_resources()
                ti_cost, _ = ct.get_harvester_cost()
                conv_cost, _ = ct.get_conveyor_cost()
                if ti >= ti_cost + conv_cost:
                    s.nav.go(ct, s.ore, lambda d: step_conv(ct, d))
                else:
                    s.nav.go(ct, s.ore, lambda d: step_walk(ct, d))

            case Patrol() as s:
                brk = self._find_break(ct)
                if brk and pos.distance_squared(brk) <= GameConstants.ACTION_RADIUS_SQ:
                    assert self.core is not None
                    d = repair_dir(ct, brk, self.core)
                    if ct.can_build_conveyor(brk, d):
                        ct.build_conveyor(brk, d)
                    s.idle_turns = 0
                    return

                ore = self._find_ore(ct)
                if ore:
                    anchor = self._nearest_connected(pos, pressure) or self.core
                    assert anchor is not None
                    self.state = WalkToAnchor(ore=ore, anchor=anchor)
                    s.idle_turns = 0
                elif self._should_raid(ct, s.idle_turns):
                    self.state = Raid()
                else:
                    s.idle_turns += 1
                    if self._retarget(s, pos):
                        patrol_target = self._pick_patrol_target(ct)
                        if patrol_target is not None:
                            s.target = patrol_target
                        else:
                            s.target = self._pick_explore_target(ct)
                        s.nav.reset()
                    if isinstance(self.state, Patrol) and s.target is not None:
                        s.nav.go(ct, s.target, lambda d: step_road(ct, d))

            case Raid() as s:
                assert self.enemy_core is not None
                enemy_infra = self._find_enemy_infra(ct)
                if enemy_infra is not None:
                    s.nav.go(ct, enemy_infra, lambda d: step_raid(ct, d))
                else:
                    target = self.enemy_core
                    at_target = pos.distance_squared(target) <= 4
                    if at_target or s.nav.unreachable:
                        target = Position(
                            random.randint(0, self.w - 1),
                            random.randint(0, self.h - 1),
                        )
                        s.nav.reset()
                    s.nav.go(ct, target, lambda d: step_raid(ct, d))

        self._propose_markers(ct, pressure)
        self.writer.flush(ct)
