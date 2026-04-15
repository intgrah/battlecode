"""Builder bot logic — explore until ore is found, then pathfind to ore."""

from __future__ import annotations

from astar import ChainAstar
from bfs import NavBfs
from cambc import Controller, EntityType, Environment, Position
from env_tracker import EnvTracker
from rax_plan import RaxPlan
from reachable import Reachable
from symmetry import Symmetry, SymmetryDetector
from ti_plan import TiPlan
from tile_codec import encode_tile
from tracker import Tracker
from unit import Unit
from utils import _ALL_DIRS, try_move_smart  # noqa: F401

_BUILDABLE = frozenset((EntityType.ROAD, EntityType.MARKER, EntityType.BARRIER, None))


def _update_nearby_tiles(
    nav: NavBfs,
    reachable: Reachable,
    sym: Symmetry,
    ct: Controller,
    tile_cache: list[int],
    env_trackers: list[EnvTracker],
    trackers: list[Tracker],
    chain: ChainAstar,
) -> None:
    """Read nearby tiles from the controller and feed raw data to nav."""
    w = nav.w
    my_team = ct.get_team()
    nearby = ct.get_nearby_tiles()
    for tile in nearby:
        i = tile.y * w + tile.x
        env = ct.get_tile_env(tile)
        bid = ct.get_tile_building_id(tile)
        building_type = ct.get_entity_type(bid) if bid is not None else None
        is_allied = bid is None or ct.get_team(bid) == my_team
        key = encode_tile(env, building_type, is_allied)
        if tile_cache[i] == key:
            continue
        tile_cache[i] = key
        nav.update_tile(i, env, building_type, is_allied, sym)
        for tracker in env_trackers:
            tracker.update_tile(i, env, building_type, is_allied, sym)
        for tracker in trackers:
            tracker.update_tile(i, env, building_type, is_allied)
        reachable.update_tile(i, env, sym)
        chain.update_tile(tile.x, tile.y, env, building_type, is_allied)
    reachable.compute(tile_cache, chain)


class Builder(Unit):
    def __init__(self, ct: Controller) -> None:
        w = ct.get_map_width()
        h = ct.get_map_height()
        self.nav = NavBfs(w, h)
        self.reachable = Reachable(w, h)
        self.sym: SymmetryDetector | None = None
        self.core_pos: Position | None = None
        self.w = w
        self.h = h
        self._tile_cache: list[int] = [0xFF] * (w * h)
        self._mirrored = False
        self.ti_ore = EnvTracker(
            w, h, Environment.ORE_TITANIUM, entity_types=_BUILDABLE, allied_only=True
        )
        self.ax_ore = EnvTracker(
            w, h, Environment.ORE_AXIONITE, entity_types=_BUILDABLE, allied_only=True
        )
        self.env_trackers: list[EnvTracker] = [self.ti_ore, self.ax_ore]
        self.allied_conveyors = Tracker(
            w, h, entity_type=EntityType.CONVEYOR, allied_only=True
        )
        self.trackers: list[Tracker] = [self.allied_conveyors]
        self.plan: RaxPlan | TiPlan
        self.need_plan = ct.get_current_round() < 5
        if ct.get_current_round() > 1:
            self.plan = TiPlan(w, h, self._tile_cache, ChainAstar(w, h), self.ti_ore)
        else:
            self.plan = RaxPlan(w, h, self._tile_cache, self.ti_ore, self.ax_ore)
        self._rr_idx: int = 0
        self.unitID: int | None = None
        self._got_ax: bool = False
        self._many_units: bool = ct.get_unit_count() > 10
        self._seen_enemy_core: bool = False

    def run(self, ct: Controller) -> None:
        pos = ct.get_position()

        if self.unitID is None:
            self.unitID = ct.get_id() % 64
        print(f"unit {self.unitID}")

        # Initialize symmetry detector once we know our core position
        if self.core_pos is None:
            my_team = ct.get_team()
            for tile in ct.get_nearby_tiles():
                bid = ct.get_tile_building_id(tile)
                if (
                    bid is not None
                    and ct.get_entity_type(bid) == EntityType.CORE
                    and ct.get_team(bid) == my_team
                ):
                    self.core_pos = ct.get_position(bid)
                    self.sym = SymmetryDetector(self.w, self.h, self.core_pos)
                    self.reachable.set_source(self.core_pos)
                    self.plan.set_core(self.core_pos)
                    break
            assert self.core_pos is not None

        # emergency core heal
        if ct.is_in_vision(self.core_pos):
            bid = ct.get_tile_building_id(self.core_pos)
            if ct.get_hp(bid) < ct.get_max_hp(bid):
                self.nav.set_goal(self.core_pos)
                if ct.can_heal(pos):
                    ct.heal(pos)
                self.nav.step(ct)
                if ct.can_heal(pos):
                    ct.heal(pos)
                return

        # Run symmetry detection
        if self.sym.resolved is Symmetry.UNKNOWN:
            for tile in ct.get_nearby_tiles():
                self.sym.update(tile.y * self.w + tile.x, tile, ct.get_tile_env(tile))

        # Once symmetry is resolved, mirror all known tiles to the BFS grid
        if not self._mirrored and self.sym.resolved is not Symmetry.UNKNOWN:
            self.nav.mirror_known(self.sym.resolved, self.sym.known_env)
            self.reachable.mirror_known(self.sym.resolved, self.sym.known_env)
            for tracker in self.env_trackers:
                tracker.mirror_known(self.sym.resolved)
            self._mirrored = True

        resolved = self.sym.resolved

        _update_nearby_tiles(
            self.nav,
            self.reachable,
            resolved,
            ct,
            self._tile_cache,
            self.env_trackers,
            self.trackers,
            self.plan.chain,
        )
        print(f"sym {resolved.name}")

        new_pos = ct.get_position()

        # Plan execution takes precedence over normal navigation. The plan
        # itself sets the nav goal each turn.
        # TiPlan bots: patrol until refined axionite arrives, then
        # begin the ore-phase to find ti ore and build the chain.
        self._got_ax |= ct.get_global_resources()[1] > 0
        if not self._seen_enemy_core and self.sym.enemy_core is not None:
            self._seen_enemy_core |= ct.is_in_vision(self.sym.enemy_core)

        if not self.need_plan:
            print("cautious patrol")
            self._patrol(ct, new_pos)
        elif isinstance(self.plan, TiPlan) and not self._got_ax:
            print("pre ax patrol")
            self._patrol(ct, new_pos)
        elif self.plan.plan_done:
            print("post plan patrol")
            self._patrol(ct, new_pos)
        else:
            fail_idx = self.plan.plan_ok()
            if self.plan.has_plan and fail_idx != -1:
                print("replanning")
                self.plan.replan(ct, fail_idx)
            if self.plan.has_plan:
                print(self.plan.plan_list[self.plan.plan_progress :])
                goal = self.plan.execute(ct)
                if goal is not None:
                    self.nav.set_goal(goal)
            else:
                self._handle_ore_phase(ct, new_pos)

        if self.plan.has_plan:
            self.plan.chain.draw_path(ct, self.plan.plan_list)

        self.nav.step(ct)
        # self.plan.chain.emit_vis()
        # self.nav.emit_vis()
        self.reachable.emit_vis()

    def _patrol(self, ct: Controller, pos: Position) -> None:
        """Round-robin patrol over allied conveyors and ti-ore tiles.
        Upgrade conveyors to armoured and barrier ore along the way.
        Prioritise healing damaged friendly buildings.
        """
        # If a visible friendly building is damaged, go heal it first.
        damaged = self._find_damaged(ct)
        if damaged is not None:
            self.nav.set_goal(damaged)
            ct.draw_indicator_line(ct.get_position(), damaged, 255, 0, 0)
            if ct.can_heal(damaged):
                ct.heal(damaged)
        else:
            patrol = (
                self.allied_conveyors.as_positions()
                + self.ti_ore.as_positions()
                + self.ax_ore.as_positions()
            )
            if patrol:
                self._rr_idx %= len(patrol)
                for _ in range(len(patrol)):
                    target = patrol[self._rr_idx]
                    if pos.distance_squared(target) > 2:
                        break
                    self._rr_idx = (self._rr_idx + 1) % len(patrol)
                self.nav.set_goal(patrol[self._rr_idx])
            else:
                self._handle_explore(ct, pos)
        self.allied_conveyors.draw_tracked(ct, 0, 200, 255)
        self.ti_ore.draw_tracked(ct, 0, 255, 255)
        self.ax_ore.draw_tracked(ct, 0, 255, 255)
        # self._upgrade_adjacent_conveyor(ct, pos)
        self._barrier_adjacent_ore(ct)

    def _consider_laucher(self, pos: Position, launcher_pos: set[Position]) -> bool:
        return all(pos.add(d) not in launcher_pos for d in _ALL_DIRS)

    def _find_damaged(self, ct: Controller) -> Position | None:
        """Return the position of a visible friendly building with less
        than max HP, or None if everything is healthy.
        """
        my_team = ct.get_team()
        for bid in ct.get_nearby_buildings():
            if ct.get_team(bid) != my_team:
                continue
            if ct.get_hp(bid) < ct.get_max_hp(bid):
                return ct.get_position(bid)
        return None

    def _upgrade_adjacent_conveyor(self, ct: Controller, pos: Position) -> None:
        """If a friendly conveyor is in action range (r²<=2), destroy it
        and rebuild as an armoured conveyor in the same direction.
        """
        ti_have, ax_have = ct.get_global_resources()
        ti_cost, ax_cost = ct.get_armoured_conveyor_cost()
        if ti_have < ti_cost or ax_have < ax_cost:
            return
        my_team = ct.get_team()
        for bid in ct.get_nearby_buildings(2):
            if ct.get_entity_type(bid) != EntityType.CONVEYOR:
                continue
            if ct.get_team(bid) != my_team:
                continue
            p = ct.get_position(bid)
            direction = ct.get_direction(bid)
            if not ct.can_destroy(p):
                return
            ct.destroy(p)
            if ct.can_build_armoured_conveyor(p, direction):
                ct.build_armoured_conveyor(p, direction)
            return

    def _barrier_adjacent_ore(self, ct: Controller) -> None:
        """If an unoccupied ti-ore tile is in action range (r²<=2),
        build a barrier on it to deny the ore from enemies.
        """
        ti_cost = ct.get_barrier_cost()[0]
        if ct.get_global_resources()[0] < ti_cost:
            return
        for tile in ct.get_nearby_tiles(2):
            i = tile.y * self.w + tile.x
            if not self.ti_ore.positions.get(i) and not self.ax_ore.positions.get(i):
                continue
            if ct.can_build_barrier(tile):
                ct.build_barrier(tile)
                return

    def _ore_env_at(self, pos: Position) -> Environment | None:
        """Return the ore type at `pos` if it's a tracked ore tile."""
        i = pos.y * self.w + pos.x
        if self.ti_ore.positions.get(i):
            return Environment.ORE_TITANIUM
        if self.ax_ore.positions.get(i):
            return Environment.ORE_AXIONITE
        return None

    def _handle_ore_phase(self, ct: Controller, pos: Position) -> None:
        """Navigate to ore and kick off the appropriate plan.

        TiPlan bots just target the nearest ti ore; RaxPlan bots do a
        two-phase walk (first ore → opposite-type ore) and begin a
        refined-axionite chain on arrival.
        """
        if isinstance(self.plan, TiPlan):
            self._handle_ti_ore_phase(ct, pos)
            return

        if self.plan.first_ore_pos is None:
            goals = self.ti_ore.as_positions() + self.ax_ore.as_positions()
            if goals:
                self.nav.set_goals(goals)
                self.ti_ore.draw_tracked(ct, 0, 255, 255)
                self.ax_ore.draw_tracked(ct, 255, 255, 0)
            else:
                print("exploring")
                self._handle_explore(ct, pos)
                return
        else:
            other = (
                self.ax_ore
                if self.plan.first_ore_env == Environment.ORE_TITANIUM
                else self.ti_ore
            )
            goals = other.as_positions()
            if goals:
                self.nav.set_goals(goals)
                other.draw_tracked(ct, 0, 255, 255)
                ct.draw_indicator_dot(self.plan.first_ore_pos, 0, 255, 0)
            else:
                print("exploring")
                self._handle_explore(ct, pos)
                return

        nearest = self.nav.nearest_goal(ct)
        if nearest is None:
            print("no nearest goal")
            return
        here = self._ore_env_at(nearest)
        if here is None:
            print("no ore at nearest")
            return
        if self.plan.first_ore_pos is None:
            self.plan.set_first_ore(nearest, here)
            return

        if here != self.plan.first_ore_env and nearest != self.plan.first_ore_pos:
            ct.draw_indicator_dot(nearest, 0, 255, 0)
            print("beginning plan")
            goal = self.plan.begin_plan(ct, self.plan.first_ore_pos, nearest)
            if goal is not None:
                self.nav.set_goal(goal)

    def _handle_ti_ore_phase(self, ct: Controller, pos: Position) -> None:
        """TiPlan: walk to the nearest ti ore tile, begin plan on arrival."""
        assert isinstance(self.plan, TiPlan)
        goals = self.ti_ore.as_positions()
        if not goals:
            print("exploring")
            self._handle_explore(ct, pos)
            return
        self.nav.set_goals(goals)
        self.ti_ore.draw_tracked(ct, 0, 255, 255)

        nearest = self.nav.nearest_goal(ct)
        if nearest is None:
            print("no nearest")
            return
        i = nearest.y * self.w + nearest.x
        if not self.ti_ore.positions.get(i):
            print("no ore on nearest")
            return
        ct.draw_indicator_dot(nearest, 0, 255, 0)
        print("beginning ti plan")
        goal = self.plan.begin_plan(ct, nearest)
        if goal is not None:
            self.nav.set_goal(goal)

    def _handle_explore(self, ct: Controller, new_pos: Position) -> None:

        self._barrier_adjacent_ore(ct)
        target = self.reachable.pick_frontier(new_pos, self.core_pos, self.sym.resolved)
        if target is not None:
            self.nav.set_goal(target)
            ct.draw_indicator_dot(target, 255, 0, 255)
