import json
import random
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from bugnav import BugNav
from cambc import Controller, EntityType, GameConstants, Position
from comms import MarkerReader, MarkerWriter
from marker import BreakAlert, PressureSummary, Threat, Urgency
from network import NetworkBelief
from params import (
    PATROL_IDLE_LIMIT,
    REPULSION_JITTER,
)
from util import CARDINALS, DIRS, ore_env, repair_dir, step_conv, step_road, step_walk

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


@dataclass
class Patrol:
    nav: BugNav = field(default_factory=BugNav)
    target: Position | None = None
    uneventful: int = 0


State = ExploreConv | ExploreRoad | WalkToAnchor | BuildChain | Patrol


class BuilderAgent:
    def __init__(self) -> None:
        self.core: Position | None = None
        self.enemy_core: Position | None = None
        self.spoke_target: Position | None = None
        self.w = 0
        self.h = 0
        self.visited: list[list[bool]] | None = None
        self.net = NetworkBelief()
        self.state: State = ExploreConv()
        self.reader = MarkerReader()
        self.writer = MarkerWriter()
        self.harvesters_built = 0
        self._gunner_placed = False
        self._recent_positions: list[tuple[int, int]] = []

    def _setup(self, ct: Controller) -> None:
        my = ct.get_team()
        self.w, self.h = ct.get_map_width(), ct.get_map_height()
        for eid in ct.get_nearby_entities():
            if ct.get_entity_type(eid) == EntityType.CORE and ct.get_team(eid) == my:
                self.core = ct.get_position(eid)
                break
        self.visited = [[False] * self.h for _ in range(self.w)]
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

    def _find_enemy_building_near_core(self, ct: Controller) -> Position | None:
        assert self.core is not None
        my = ct.get_team()
        for t in ct.get_nearby_tiles():
            bid = ct.get_tile_building_id(t)
            if bid is None or ct.get_team(bid) == my:
                continue
            if t.distance_squared(self.core) <= 36:
                return t
        return None

    def _try_place_harvester(self, ct: Controller, ore: Position) -> bool:
        my = ct.get_team()
        for cd in CARDINALS:
            adj = ore.add(cd)
            if not (0 <= adj.x < self.w and 0 <= adj.y < self.h):
                continue
            bid = ct.get_tile_building_id(adj)
            if bid is not None and ct.get_team(bid) == my:
                et = ct.get_entity_type(bid)
                if et in (
                    EntityType.CONVEYOR,
                    EntityType.ARMOURED_CONVEYOR,
                    EntityType.SPLITTER,
                ):
                    if ct.can_build_harvester(ore):
                        ct.build_harvester(ore)
                        return True
                    return False
        return False

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

    def _nearest_connected(self, pos: Position) -> Position | None:
        best: Position | None = None
        best_dist = 999999
        for p in self.net.connected_tiles():
            d = pos.distance_squared(p)
            if d < best_dist:
                best_dist = d
                best = p
        return best

    def _has_cardinal_conveyor(self, ct: Controller, ore: Position) -> bool:
        my = ct.get_team()
        for d in CARDINALS:
            adj = ore.add(d)
            if not ct.is_in_vision(adj):
                continue
            bid = ct.get_tile_building_id(adj)
            if (
                bid is not None
                and ct.get_team(bid) == my
                and ct.get_entity_type(bid) in _DESTRUCTIBLE
            ):
                return True
        return False

    def _ensure_cardinal_conveyor(
        self,
        ct: Controller,
        pos: Position,
        ore: Position,
    ) -> None:
        for d in CARDINALS:
            adj = ore.add(d)
            if not ct.is_in_vision(adj):
                continue
            out_dir = adj.direction_to(pos)
            if ct.can_build_conveyor(adj, out_dir):
                ct.build_conveyor(adj, out_dir)
                return

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

    def _pick_unvisited_target(self, ct: Controller) -> Position | None:
        if self.visited is None:
            return None
        pos = ct.get_position()
        best: Position | None = None
        best_dist = 999999
        step = 3
        for x in range(0, self.w, step):
            for y in range(0, self.h, step):
                if not self.visited[x][y]:
                    d = (pos.x - x) ** 2 + (pos.y - y) ** 2
                    if d < best_dist:
                        best_dist = d
                        best = Position(x, y)
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
        t = Position(
            max(0, min(self.w - 1, pos.x + dx * self.w)),
            max(0, min(self.h - 1, pos.y + dy * self.h)),
        )
        self.spoke_target = t
        return t

    def _retarget(self, s: ExploreConv | ExploreRoad | Patrol, pos: Position) -> bool:
        if s.target is None:
            return True
        if s.nav.unreachable:
            s.nav.unreachable = False
            return True
        return pos.x == s.target.x and pos.y == s.target.y

    def _emit_debug(
        self,
        ct: Controller,
        action: str = "",
        **extra: str | int | bool | list[int],
    ) -> None:
        """Emit structured debug JSON to stdout for replay_debug.py."""
        pos = ct.get_position()
        state = self.state
        dbg = {
            "_dbg": True,
            "state": type(state).__name__,
            "pos": [pos.x, pos.y],
            "action": action,
            "target": [t.x, t.y] if (t := getattr(state, "target", None)) else None,
            "net_connected": len(self.net.connected_tiles()),
            "net_dead": [
                [p.x, p.y] for p in self.net.tiles if self.net.tiles[p].is_dead
            ],
            "threats": len(self.reader.threats),
            "breaks": len(self.reader.breaks),
            "claims": len(self.reader.claims),
            "harvesters_built": self.harvesters_built,
        }
        if isinstance(state, Patrol):
            dbg["uneventful"] = state.uneventful
        dbg.update(extra)
        print(json.dumps(dbg, separators=(",", ":")))

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

        cong = self.net.most_congested(self.core)
        if cong:
            info = self.net.get(cong)
            flow_int = min(15, int(info.flow * 4)) if info else 0
            self.writer.propose(
                pos,
                PressureSummary(
                    pos_x=cong.x,
                    pos_y=cong.y,
                    pressure_level=flow_int,
                    upstream_harvesters=flow_int,
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
        if self.visited is not None:
            for t in ct.get_nearby_tiles():
                self.visited[t.x][t.y] = True

        pos = ct.get_position()
        ct.get_team()
        rnd = ct.get_current_round()

        if rnd % 50 == 0:
            self.net.dump(
                str(Path(tempfile.gettempdir()) / "v32_belief.jsonl"),
                rnd,
                ct.get_id(),
                (pos.x, pos.y),
            )

        if (
            not self._gunner_placed
            and pos.distance_squared(self.core) <= 8
            and rnd >= 20
        ):
            assert self.enemy_core is not None
            if self._try_build_gunner(ct, pos) or self._try_build_gunner(ct, self.core):
                self._gunner_placed = True
                return

        brk = self.net.find_break(ct, self.core)
        if brk:
            with (Path(tempfile.gettempdir()) / "v32_debug.txt").open("a") as f:
                f.write(
                    f"t{ct.get_current_round()} bot@{pos} FOUND brk@{brk} dist={pos.distance_squared(brk)}\n",
                )
        if brk:
            dist = pos.distance_squared(brk)
            if dist <= GameConstants.ACTION_RADIUS_SQ:
                bid = ct.get_tile_building_id(brk)
                if bid is not None and ct.get_entity_type(bid) in (
                    EntityType.ROAD,
                    EntityType.MARKER,
                ):
                    ct.destroy(brk)
                d = repair_dir(ct, brk, self.core)
                ok = ct.can_build_conveyor(brk, d)
                if ok:
                    ct.build_conveyor(brk, d)
                ti, _ = ct.get_global_resources()
                with (Path(tempfile.gettempdir()) / "v32_debug.txt").open("a") as f:
                    f.write(
                        f"t{rnd} bot@{pos} REPAIR brk@{brk} built={ok} ti={ti} d={d}\n",
                    )
                self._propose_markers(ct)
                self.writer.flush(ct)
                return
            s = self.state
            if isinstance(s, (ExploreConv, Patrol)):
                s.target = brk
                s.nav.reset()
                s.nav.go(ct, brk, lambda d: step_road(ct, d))
                self._propose_markers(ct)
                self.writer.flush(ct)
                return

        enemy = self._find_enemy_near_core(ct)
        enemy_building_near_core = self._find_enemy_building_near_core(ct)
        threat = enemy or enemy_building_near_core
        if threat and pos.distance_squared(self.core) <= 100:
            if pos.distance_squared(
                self.core,
            ) <= GameConstants.ACTION_RADIUS_SQ and ct.can_heal(self.core):
                ct.heal(self.core)
                return
            s = self.state
            if isinstance(s, (ExploreConv, ExploreRoad, Patrol)):
                s.target = self.core
                s.nav.reset()
                s.nav.go(ct, self.core, lambda d: step_walk(ct, d))
                self._propose_markers(ct)
                self.writer.flush(ct)
                return

        ct.get_current_round()

        match self.state:
            case ExploreConv() as s:
                ore = self._find_ore(ct)
                if ore and pos.distance_squared(ore) <= GameConstants.ACTION_RADIUS_SQ:
                    if self._try_place_harvester(ct, ore):
                        self.harvesters_built += 1
                        ore = self._find_ore(ct)
                    else:
                        ore = None
                if ore and (s.target is None or s.target != ore):
                    s.target = ore
                    s.nav.reset()
                elif not ore and self._retarget(s, pos):
                    if s.target is None:
                        s.target = self._initial_target(ct)
                    elif self.spoke_target is not None:
                        if pos.distance_squared(self.spoke_target) <= 4:
                            unv = self._pick_unvisited_target(ct)
                            s.target = unv or self._pick_explore_target(ct)
                        else:
                            s.target = self.spoke_target
                    else:
                        unv = self._pick_unvisited_target(ct)
                        s.target = unv or self._pick_explore_target(ct)
                    s.nav.reset()
                if s.target is not None:
                    s.nav.go(ct, s.target, lambda d: step_conv(ct, d))
                if not ore and s.target is not None:
                    assert self.core is not None
                    far_enough = pos.distance_squared(self.core) >= 100
                    arrived = pos.x == s.target.x and pos.y == s.target.y
                    unreachable = s.nav.unreachable
                    if arrived or unreachable or far_enough:
                        self.state = ExploreRoad()
                        return

            case ExploreRoad() as s:
                ore = self._find_ore(ct)
                if ore:
                    anchor = self._nearest_connected(pos) or self.core
                    assert anchor is not None
                    self.state = WalkToAnchor(ore=ore, anchor=anchor)
                    return
                if self._retarget(s, pos):
                    if s.target is None:
                        s.target = self._initial_target(ct)
                    else:
                        unv = self._pick_unvisited_target(ct)
                        s.target = unv or self._pick_explore_target(ct)
                    s.nav.reset()
                if s.target is not None:
                    s.nav.go(ct, s.target, lambda d: step_road(ct, d))
                if (
                    s.target is not None
                    and (pos == s.target or s.nav.unreachable)
                    and self._pick_unvisited_target(ct) is None
                ):
                    self.state = Patrol()
                    return

            case WalkToAnchor() as s:
                if pos.distance_squared(s.anchor) <= GameConstants.ACTION_RADIUS_SQ:
                    d = pos.direction_to(s.anchor)
                    if ct.can_build_conveyor(pos, d):
                        ct.build_conveyor(pos, d)
                    self.state = BuildChain(ore=s.ore)
                    return
                s.nav.go(ct, s.anchor, lambda d: step_road(ct, d))

            case BuildChain() as s:
                if pos.distance_squared(s.ore) == 1:
                    if not self._has_cardinal_conveyor(ct, s.ore):
                        self._ensure_cardinal_conveyor(ct, pos, s.ore)
                    elif ct.can_build_harvester(s.ore):
                        ct.build_harvester(s.ore)
                        self.harvesters_built += 1
                        self.state = ExploreRoad()
                    return
                ti, _ = ct.get_global_resources()
                ti_cost, _ = ct.get_harvester_cost()
                conv_cost, _ = ct.get_conveyor_cost()
                if ti < ti_cost + conv_cost:
                    return
                s.nav.go(ct, s.ore, lambda d: step_conv(ct, d))

            case Patrol() as s:
                dead = self.net.dead_conveyor()
                if (
                    dead
                    and pos.distance_squared(dead) <= GameConstants.ACTION_RADIUS_SQ
                ):
                    ct.destroy(dead)
                    if ct.can_build_road(dead):
                        ct.build_road(dead)
                    s.uneventful = 0
                    return

                if dead:
                    s.target = dead
                    s.nav.reset()
                    s.uneventful = 0
                    s.nav.go(ct, s.target, lambda d: step_walk(ct, d))
                    return

                ore = self._find_ore(ct)
                if ore:
                    anchor = self._nearest_connected(pos) or self.core
                    assert anchor is not None
                    self.state = WalkToAnchor(ore=ore, anchor=anchor)
                    s.uneventful = 0
                    return
                if s.uneventful >= PATROL_IDLE_LIMIT:
                    self.state = ExploreRoad()
                elif self._retarget(s, pos):
                    s.uneventful += 1
                    chain_t = self._pick_chain_target()
                    if chain_t:
                        s.target = chain_t
                    else:
                        s.target = self._pick_explore_target(ct)
                    s.nav.reset()
                if isinstance(self.state, Patrol) and s.target is not None:
                    s.nav.go(ct, s.target, lambda d: step_walk(ct, d))

        self._emit_debug(ct, "tick")
        self._propose_markers(ct)
        self.writer.flush(ct)
