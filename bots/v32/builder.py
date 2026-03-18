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
    DEFENSE_MIN_HARVESTERS,
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
class Patrol:
    nav: BugNav = field(default_factory=BugNav)
    target: Position | None = None
    uneventful: int = 0


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

    def _emit_debug(self, ct: Controller, action: str = "", **extra: str | int | bool | list[int]) -> None:
        """Emit structured debug JSON to stdout for replay_debug.py."""
        pos = ct.get_position()
        state = self.state
        dbg = {
            "_dbg": True,
            "state": type(state).__name__,
            "pos": [pos.x, pos.y],
            "action": action,
            "target": [state.target.x, state.target.y]
            if hasattr(state, "target") and state.target
            else None,
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

        pos = ct.get_position()
        my = ct.get_team()

        brk = self.net.find_break(ct, self.core)
        if brk:
            with (Path(tempfile.gettempdir()) / "v32_debug.txt").open("a") as f:
                f.write(
                    f"t{ct.get_current_round()} bot@{pos} FOUND brk@{brk} dist={pos.distance_squared(brk)}\n",
                )
        if brk:
            if pos.distance_squared(brk) <= GameConstants.ACTION_RADIUS_SQ:
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
                self._emit_debug(ct, "repair", brk=[brk.x, brk.y], built=ok, ti=ti)
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
        if enemy and pos.distance_squared(self.core) <= 36:
            s = self.state
            if isinstance(s, (ExploreConv, Patrol)):
                s.nav.go(ct, enemy, lambda d: step_road(ct, d))
                self._emit_debug(ct, "defend_core", enemy=[enemy.x, enemy.y])
                self._propose_markers(ct)
                self.writer.flush(ct)
                return

        ct.get_current_round()

        match self.state:
            case ExploreConv() as s:
                ore = self._find_ore(ct)
                if ore and pos.distance_squared(ore) <= GameConstants.ACTION_RADIUS_SQ:
                    has_cardinal_conv = False
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
                                has_cardinal_conv = True
                                break
                    can = ct.can_build_harvester(ore)
                    if has_cardinal_conv and can:
                        ct.build_harvester(ore)
                        self.harvesters_built += 1
                        if self.harvesters_built >= DEFENSE_MIN_HARVESTERS:
                            self._try_build_gunner(ct, self.core)
                        return
                    if pos.distance_squared(ore) == 1:
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
                    s.nav.go(ct, s.target, lambda d: step_conv(ct, d))

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
                    self.state = ExploreConv(target=ore)
                    s.uneventful = 0
                elif s.uneventful >= PATROL_IDLE_LIMIT:
                    self.state = ExploreConv()
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
