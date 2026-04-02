import random
from enum import Enum

from bugnav import BugNav
from cambc import Controller, Direction, EntityType, GameConstants, Position
from core import IDLE_BEFORE_RAID, RAID_START
from util import (
    DIRS,
    ib,
    ore_env,
    repair_dir,
    step_conv,
    step_raid,
    step_road,
    step_walk,
    toward,
    wall,
)


class BuilderState(Enum):
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
        self.state = BuilderState.EXPLORE
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
            self.state = BuilderState.RAID

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

        if self.state not in (
            BuilderState.RAID,
            BuilderState.CHAIN_BUILD,
            BuilderState.RETURN,
        ):
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

        match self.state:
            case BuilderState.EXPLORE:
                self._do_explore(ct, pos)
            case BuilderState.SEEK_ORE:
                self._do_seek_ore(ct, pos)
            case BuilderState.RETURN:
                self._do_return(ct, pos)
            case BuilderState.CHAIN_BUILD:
                self._do_chain_build(ct, pos)
            case BuilderState.MAINTAIN:
                self._do_maintain(ct, pos)
            case BuilderState.PATROL:
                self._do_patrol(ct, pos)
            case BuilderState.FORTIFY:
                self._do_fortify(ct, pos)
            case BuilderState.RAID:
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

    def _find_defense_conv(self, ct: Controller) -> Position | None:
        assert self.core is not None
        assert self.enemy_core is not None
        my = ct.get_team()
        enemy_dir = toward(self.core, self.enemy_core)
        best = None
        best_dist = 999999
        for t in ct.get_nearby_tiles():
            bid = ct.get_tile_building_id(t)
            if bid is None or ct.get_team(bid) != my:
                continue
            et = ct.get_entity_type(bid)
            if et != EntityType.CONVEYOR:
                continue
            core_dist = t.distance_squared(self.core)
            if core_dist <= 4 or core_dist > 49:
                continue
            enemy_side = toward(self.core, t)
            if (
                enemy_side == enemy_dir
                or enemy_side == enemy_dir.rotate_left()
                or enemy_side == enemy_dir.rotate_right()
            ) and core_dist < best_dist:
                best_dist = core_dist
                best = t
        if best:
            return best
        for t in ct.get_nearby_tiles():
            bid = ct.get_tile_building_id(t)
            if bid is None or ct.get_team(bid) != my:
                continue
            et = ct.get_entity_type(bid)
            if et != EntityType.CONVEYOR:
                continue
            core_dist = t.distance_squared(self.core)
            if core_dist <= 4 or core_dist > 49:
                continue
            if core_dist < best_dist:
                best_dist = core_dist
                best = t
        return best

    def _ore_would_connect(self, ct: Controller, pos: Position, ore: Position) -> bool:
        my = ct.get_team()
        for d in Direction:
            adj = pos.add(d)
            if adj.x == ore.x and adj.y == ore.y:
                continue
            if not ib(ct, adj):
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
            conv_dir = ct.get_direction(bid)
            dx, dy = conv_dir.delta()
            out_pos = Position(adj.x + dx, adj.y + dy)
            if out_pos.x == ore.x and out_pos.y == ore.y:
                continue
            return True
        bid_here = ct.get_tile_building_id(pos)
        if bid_here and ct.get_team(bid_here) == my:
            et = ct.get_entity_type(bid_here)
            if et in (
                EntityType.CONVEYOR,
                EntityType.ARMOURED_CONVEYOR,
                EntityType.SPLITTER,
            ):
                conv_dir = ct.get_direction(bid_here)
                dx, dy = conv_dir.delta()
                out_pos = Position(pos.x + dx, pos.y + dy)
                if not (out_pos.x == ore.x and out_pos.y == ore.y):
                    return True
        return False

    # --- States ---

    def _do_explore(self, ct: Controller, pos: Position) -> None:
        adj = self._find_adj_ore(ct, pos)
        if adj:
            self.visited_ore.add((adj.x, adj.y))
            self.ore_target = adj
            self.state = BuilderState.RETURN
            self.nav.reset()
            return

        ore = self._find_visible_ore(ct, pos)
        if ore:
            self.state = BuilderState.SEEK_ORE
            self.target = ore
            self.nav.reset()
            return

        self.idle_turns += 1
        if self.has_income and self.idle_turns >= IDLE_BEFORE_RAID:
            self.state = BuilderState.RAID
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
            self.state = BuilderState.RETURN
            self.nav.reset()
            return

        if self.target is None:
            self.state = BuilderState.EXPLORE
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
                self.state = BuilderState.EXPLORE
                self._new_explore_target(ct, pos)
            return

        self.nav.go(ct, self.target, lambda d: step_road(ct, d))
        if self.nav.unreachable:
            self.nav.unreachable = False
            self.state = BuilderState.EXPLORE
            self._new_explore_target(ct, ct.get_position())

    def _do_return(self, ct: Controller, pos: Position) -> None:
        assert self.core is not None
        if pos.distance_squared(self.core) <= 2:
            self.state = BuilderState.CHAIN_BUILD
            self.nav.reset()
            return

        self.nav.go(ct, self.core, lambda d: step_walk(ct, d))

    def _do_chain_build(self, ct: Controller, pos: Position) -> None:
        if not self.ore_target:
            self.state = BuilderState.EXPLORE
            return

        if ct.can_build_harvester(self.ore_target) and self._ore_would_connect(
            ct,
            pos,
            self.ore_target,
        ):
            ct.build_harvester(self.ore_target)
            self.harvesters_built += 1
            self.state = BuilderState.MAINTAIN
            self.idle_turns = 0
            self.ore_target = None
            return

        if ct.is_in_vision(self.ore_target) and (
            not ore_env(ct, self.ore_target)
            or ct.get_tile_building_id(self.ore_target) is not None
        ):
            self.ore_target = None
            self.state = BuilderState.EXPLORE
            self._new_explore_target(ct, pos)
            return

        self.nav.go(ct, self.ore_target, lambda d: step_conv(ct, d))
        if self.nav.unreachable:
            self.nav.unreachable = False
            self.ore_target = None
            self.state = BuilderState.EXPLORE
            self._new_explore_target(ct, ct.get_position())

    def _do_maintain(self, ct: Controller, pos: Position) -> None:
        assert self.core is not None
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

        enemy_near_core = False
        my = ct.get_team()
        for eid in ct.get_nearby_entities():
            if (
                ct.get_team(eid) != my
                and ct.get_entity_type(eid) == EntityType.BUILDER_BOT
            ) and self.core.distance_squared(ct.get_position(eid)) <= 100:
                enemy_near_core = True
                break

        should_fortify = (
            self.harvesters_built >= 1
            and not self.has_fortified
            and ((ti > 200 and rnd > 100) or enemy_near_core)
        )
        if should_fortify:
            fl = self._find_defense_conv(ct)
            if fl:
                self.fortify_target = fl
                self.fortify_step = 1
                self.state = BuilderState.FORTIFY
                self.nav.reset()
                return

        self.idle_turns += 1
        if self.idle_turns >= IDLE_BEFORE_RAID and self.has_income:
            self.state = BuilderState.RAID
            self.nav.reset()
            return

        if self.idle_turns > 20:
            self.state = BuilderState.PATROL
            self._new_explore_target(ct, ct.get_position())
            return

        if self.core and pos.distance_squared(self.core) > 4:
            self.nav.go(ct, self.core, lambda d: step_walk(ct, d))

    def _do_fortify(self, ct: Controller, pos: Position) -> None:
        assert self.core is not None
        assert self.enemy_core is not None
        if not self.fortify_target:
            self.state = BuilderState.MAINTAIN
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
                self.state = BuilderState.MAINTAIN
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
                self.state = BuilderState.MAINTAIN
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
                    self.state = BuilderState.MAINTAIN
                    self.idle_turns = 0
                    return

            self.fortify_target = None
            self.fortify_step = 0
            self.has_fortified = True
            self.state = BuilderState.MAINTAIN
            self.idle_turns = 0

    def _do_patrol(self, ct: Controller, pos: Position) -> None:
        adj = self._find_adj_ore(ct, pos)
        if adj:
            self.visited_ore.add((adj.x, adj.y))
            self.ore_target = adj
            self.state = BuilderState.RETURN
            self.nav.reset()
            return

        ore = self._find_visible_ore(ct, pos)
        if ore:
            self.state = BuilderState.SEEK_ORE
            self.target = ore
            self.nav.reset()
            return

        brk = self._find_break(ct)
        if brk:
            self.state = BuilderState.MAINTAIN
            self.idle_turns = 0
            return

        if self.has_income and self.idle_turns >= IDLE_BEFORE_RAID:
            self.state = BuilderState.RAID
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
        assert self.core is not None
        assert self.enemy_core is not None
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
