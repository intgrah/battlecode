import random
from dataclasses import dataclass, field

from bugnav import BugNav
from cambc import Controller, EntityType, GameConstants, Position
from util import CARDINALS, DIRS, ore_env, step_conv, step_road

_TRANSPORT = frozenset(
    {
        EntityType.CONVEYOR,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.SPLITTER,
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


State = ExploreConv | ExploreRoad | WalkToAnchor | BuildChain


class BuilderAgent:
    def __init__(self) -> None:
        # Constants
        self.core: Position | None = None
        self.enemy_core: Position | None = None
        self.w = 0
        self.h = 0
        # State
        self.connected: dict[Position, bool] = {}
        self.state: State = ExploreConv()

    def _setup(self, ct: Controller) -> None:
        """Find allied core and compute enemy core position."""
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
        """Trace each visible transport tile's output chain. Mark True if it reaches core, False if it dead-ends, leave unknown if it exits vision."""
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

    def _find_ore(self, ct: Controller) -> Position | None:
        """Return the closest visible unharvested ore tile, or None."""
        pos = ct.get_position()
        best: Position | None = None
        best_dist = 999999
        for t in ct.get_nearby_tiles():
            if ore_env(ct, t) and ct.get_tile_building_id(t) is None:
                d = pos.distance_squared(t)
                if d < best_dist:
                    best_dist = d
                    best = t
        return best

    def _nearest_connected(self, pos: Position) -> Position | None:
        """Return the closest known-connected transport tile, or None."""
        best: Position | None = None
        best_dist = 999999
        for p, is_connected in self.connected.items():
            if not is_connected:
                continue
            d = pos.distance_squared(p)
            if d < best_dist:
                best_dist = d
                best = p
        return best

    def _pick_explore_target(self, ct: Controller) -> Position:
        """Pick an explore target using repulsion from visible allied builders."""
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
        fx += random.uniform(-0.3, 0.3)
        fy += random.uniform(-0.3, 0.3)
        if fx == 0.0 and fy == 0.0:
            d = random.choice(DIRS)
            fx, fy = d.delta()
        scale = max(self.w, self.h) // 2
        tx = max(0, min(self.w - 1, round(pos.x + fx * scale)))
        ty = max(0, min(self.h - 1, round(pos.y + fy * scale)))
        return Position(tx, ty)

    def _initial_target(self, ct: Controller) -> Position:
        """Project spawn direction to map edge for first explore target."""
        assert self.core is not None
        pos = ct.get_position()
        d = self.core.direction_to(pos)
        dx, dy = d.delta()
        return Position(
            max(0, min(self.w - 1, pos.x + dx * self.w)),
            max(0, min(self.h - 1, pos.y + dy * self.h)),
        )

    def _retarget(self, s: ExploreConv | ExploreRoad, pos: Position) -> bool:
        """Return True if the explore state needs a new target."""
        if s.target is None:
            return True
        if s.nav.unreachable:
            s.nav.unreachable = False
            return True
        return pos.x == s.target.x and pos.y == s.target.y

    def _has_cardinal_conveyor(self, ct: Controller, ore: Position) -> bool:
        """Check if ore tile has a cardinal neighbor with an allied transport building."""
        my = ct.get_team()
        for d in CARDINALS:
            adj = ore.add(d)
            if not ct.is_in_vision(adj):
                continue
            bid = ct.get_tile_building_id(adj)
            if (
                bid is not None
                and ct.get_team(bid) == my
                and ct.get_entity_type(bid) in _TRANSPORT
            ):
                return True
        return False

    def _ensure_cardinal_conveyor(
        self,
        ct: Controller,
        pos: Position,
        ore: Position,
    ) -> None:
        """Build a conveyor on a cardinal neighbor of ore, pointing toward the builder (existing chain)."""
        for d in CARDINALS:
            adj = ore.add(d)
            if not ct.is_in_vision(adj):
                continue
            out_dir = adj.direction_to(pos)
            if ct.can_build_conveyor(adj, out_dir):
                ct.build_conveyor(adj, out_dir)
                return

    def run(self, ct: Controller) -> None:
        if self.core is None:
            self._setup(ct)
        if self.core is None:
            return

        self._update_connected(ct)
        pos = ct.get_position()

        match self.state:
            case ExploreConv() as s:
                ore = self._find_ore(ct)
                if ore and pos.distance_squared(ore) == 1:
                    if not self._has_cardinal_conveyor(ct, ore):
                        self._ensure_cardinal_conveyor(ct, pos, ore)
                    elif ct.can_build_harvester(ore):
                        ct.build_harvester(ore)
                    return
                # Reserve Ti for harvester — don't build conveyors unless affordable
                ti, _ = ct.get_global_resources()
                ti_cost, _ = ct.get_harvester_cost()
                conv_cost, _ = ct.get_conveyor_cost()
                if ti < ti_cost + conv_cost:
                    return
                if ore:
                    if s.target is None or s.target.x != ore.x or s.target.y != ore.y:
                        s.target = ore
                        s.nav.reset()
                    s.nav.go(ct, ore, lambda d: step_conv(ct, d))
                    return
                if self._retarget(s, pos):
                    if s.target is None:
                        s.target = self._initial_target(ct)
                    else:
                        s.target = self._pick_explore_target(ct)
                    s.nav.reset()
                assert s.target is not None
                s.nav.go(ct, s.target, lambda d: step_conv(ct, d))

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
                        s.target = self._pick_explore_target(ct)
                    s.nav.reset()
                assert s.target is not None
                s.nav.go(ct, s.target, lambda d: step_road(ct, d))

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
                    if ct.can_build_harvester(s.ore):
                        ct.build_harvester(s.ore)
                        self.state = ExploreRoad()
                    return
                # Reserve Ti for harvester — don't build conveyors unless affordable
                ti, _ = ct.get_global_resources()
                ti_cost, _ = ct.get_harvester_cost()
                conv_cost, _ = ct.get_conveyor_cost()
                if ti < ti_cost + conv_cost:
                    return
                s.nav.go(ct, s.ore, lambda d: step_conv(ct, d))
