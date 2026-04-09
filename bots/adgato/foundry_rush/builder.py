"""Builder bot logic — explore until ore is found, then pathfind to ore."""

from __future__ import annotations

from astar import BuildInstruction, ChainAstar
from bfs import NavBfs
from reachable import Reachable
from cambc import Controller, Direction, EntityType, Environment, Position
from explore import ExploreGrid
from symmetry import Symmetry, SymmetryDetector
from tile_codec import UNSEEN, _ET_INT, encode_tile, tile_building_type, tile_is_allied
from env_tracker import EnvTracker
from tracker import Tracker
from unit import Unit
from utils import _ALL_DIRS, in_bounds, try_move_away

_BUILDABLE = frozenset((EntityType.ROAD, EntityType.MARKER, None))

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
        is_allied = bid is not None and ct.get_team(bid) == my_team
        key = encode_tile(env, building_type, is_allied)
        if tile_cache[i] == key:
            continue
        tile_cache[i] = key
        nav.update_tile(i, env, building_type, is_allied, sym)
        for tracker in env_trackers:
            tracker.update_tile(i, env, building_type, is_allied, sym)
        for tracker in trackers:
            tracker.update_tile(i, env, building_type, is_allied)
        reachable.update_tile(i, env)
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
        self.explore = ExploreGrid(w, h)
        self.ti_ore = EnvTracker(w, h, Environment.ORE_TITANIUM, entity_types=_BUILDABLE)
        self.ax_ore = EnvTracker(w, h, Environment.ORE_AXIONITE, entity_types=_BUILDABLE)
        self.env_trackers: list[EnvTracker] = [self.ti_ore, self.ax_ore]
        self.allied_conveyors = Tracker(
            w, h, entity_type=EntityType.CONVEYOR, allied_only=True
        )
        self.trackers: list[Tracker] = [self.allied_conveyors]
        self.chain = ChainAstar(w, h)
        self._chain_plan: list[BuildInstruction] | None = None
        self._plan_progress: int = 0
        self._stage2_start: int = 0
        self.first_ore_pos: Position | None = None
        self.first_ore_env: Environment | None = None
        self.plan_done: bool = False
        self.first_offset: tuple[int, int] | None = None
        self.unitID: int | None = None

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
                    self.chain.update_tile(self.core_pos.x, self.core_pos.y, Environment.EMPTY, EntityType.CORE, True, force_update=True)
                    break
            assert self.core_pos is not None

        # Run symmetry detection
        if self.sym.resolved is Symmetry.UNKNOWN:
            for tile in ct.get_nearby_tiles():
                self.sym.update(tile.y * self.w + tile.x, tile, ct.get_tile_env(tile))

        # Once symmetry is resolved, mirror all known tiles to the BFS grid
        if not self._mirrored and self.sym.resolved is not Symmetry.UNKNOWN:
            self.nav.mirror_known(self.sym.resolved, self.sym.known_env)
            for tracker in self.env_trackers:
                tracker.mirror_known(self.sym.resolved)
            self._mirrored = True

        resolved = self.sym.resolved

        _update_nearby_tiles(
            self.nav, self.reachable, resolved, ct, self._tile_cache,
            self.env_trackers, self.trackers, self.chain,
        )
        self.explore.update(ct, pos, self.core_pos)

        print(f"sym {resolved.name}")

        new_pos = ct.get_position()


        # Plan execution takes precedence over normal navigation. The plan
        # itself sets the nav goal each turn.
        if self.plan_done:
            if self.allied_conveyors.take_changed(ct.get_current_round()):
                self.nav.set_goals(self.allied_conveyors.as_positions())
            self.allied_conveyors.draw_tracked(ct, 0, 200, 255)
            self._upgrade_adjacent_conveyor(ct, new_pos)
        else:
            fail_idx = self.plan_ok(ct)
            if self._chain_plan is not None and fail_idx != -1:
                self._replan(ct, fail_idx)
            if self._chain_plan is not None:
                print(self._chain_plan[self._plan_progress:])
                self._execute_plan(ct)
            else:
                self._handle_ore_phase(ct, new_pos)

        if self._chain_plan is not None:
            self.chain.draw_path(ct, self._chain_plan)
        self.chain.emit_vis()

        self.nav.step(ct)
        self.nav.emit_vis()


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

    def _ore_env_at(self, pos: Position) -> Environment | None:
        """Return the ore type at `pos` if it's a tracked ore tile."""
        i = pos.y * self.w + pos.x
        if self.ti_ore.positions.get(i):
            return Environment.ORE_TITANIUM
        if self.ax_ore.positions.get(i):
            return Environment.ORE_AXIONITE
        return None

    def _handle_ore_phase(self, ct: Controller, pos: Position) -> None:
        """Two-phase ore acquisition:
        Phase 1: navigate to the union of all known ti/ax ore. On arrival,
                 record the ore type and position.
        Phase 2: navigate to ore of the OPPOSITE type. On arrival, build
                 a chain plan from the first ore to the second.
        """
        if self.first_ore_pos is None:
            r = ct.get_current_round()
            ti_changed = self.ti_ore.take_changed(r)
            ax_changed = self.ax_ore.take_changed(r)
            goals = self.ti_ore.as_positions() + self.ax_ore.as_positions()
            if goals:
                if ti_changed or ax_changed:
                    self.nav.set_goals(goals)
                self.ti_ore.draw_tracked(ct, 0, 255, 255)
                self.ax_ore.draw_tracked(ct, 255, 255, 0)
            else:
                self.nav.set_goal(self.explore.target)
                self._handle_explore(ct, pos)
                return
        else:
            other = (
                self.ax_ore
                if self.first_ore_env == Environment.ORE_TITANIUM
                else self.ti_ore
            )
            goals = other.as_positions()
            if goals:
                if other.take_changed(ct.get_current_round()):
                    self.nav.set_goals(goals)
                other.draw_tracked(ct, 0, 255, 255)
                ct.draw_indicator_dot(self.first_ore_pos, 0, 255, 0)
            else:
                self.nav.set_goal(self.explore.target)
                self._handle_explore(ct, pos)
                return

        nearest = self.nav.nearest_goal(ct)
        if nearest is None or not self.reachable.is_reachable(nearest):
            return
        here = self._ore_env_at(nearest)
        if here is None:
            return
        if self.first_ore_pos is None:
            self.first_ore_pos = nearest
            self.first_ore_env = here
            # Force a phase-2 goal update now: phase 1 already consumed
            # the opposite tracker's change flag this round, so the next
            # call to take_changed() would return False and the nav would
            # never be redirected.
            other = (
                self.ax_ore if here == Environment.ORE_TITANIUM else self.ti_ore
            )
            other_goals = other.as_positions()
            if other_goals:
                self.nav.set_goals(other_goals)
            return
        
        if here != self.first_ore_env and nearest != self.first_ore_pos:
            ct.draw_indicator_dot(nearest, 0, 255, 0)
            self._chain_plan = self._chain_plan_from(
                ct, self.first_ore_pos, nearest
            )
            self._plan_progress = 0
            if self._chain_plan:
                _, gpos, _ = self._chain_plan[0]
                self.nav.set_goal(gpos)

    def _execute_plan(self, ct: Controller) -> None:
        """Pathfind to the next instruction's tile and try to place its
        building. On a successful build, advance `_plan_progress`. When
        we run off the end of the plan, clear it.
        """
        entity, pos, extra = self._chain_plan[self._plan_progress]

        if self._try_place(ct, entity, pos, extra):
            self._plan_progress += 1
        
        if self._plan_progress >= len(self._chain_plan):
            self._chain_plan = None
            self._plan_progress = 0
            self.plan_done = True
            return
        
        _, pos, _ = self._chain_plan[self._plan_progress]
        self.nav.set_goal(pos)

    def _try_place(
        self,
        ct: Controller,
        entity: EntityType,
        pos: Position,
        extra: object,
    ) -> bool:
        # Clear any road sitting on the target tile first. We only act if
        # we've actually observed the tile (not UNSEEN). Allied roads are
        # destroyed; enemy roads are fired upon.
        
        cached = self._tile_cache[pos.y * self.w + pos.x]
        if cached != UNSEEN and tile_building_type(cached) == EntityType.ROAD:
            if tile_is_allied(cached):
                if ct.can_destroy(pos):
                    ct.destroy(pos)
            else:
                if ct.can_fire(pos):
                    ct.fire(pos)

        if entity == EntityType.CORE:
            # Special flag: destroy whatever allied building is at pos.
            if cached == UNSEEN:
                return False
            ttype = tile_building_type(cached)
            if ttype is not None:
                if not ct.can_destroy(pos):
                    return False
                ct.destroy(pos)
            
            self._plan_progress += 1
            entity, pos, extra = self._chain_plan[self._plan_progress]
        
        if entity == EntityType.HARVESTER:
            if ct.get_position() == pos:
                try_move_away(ct, pos)
            if not ct.can_build_harvester(pos):
                return False
            ct.build_harvester(pos)
            return True
        if entity == EntityType.FOUNDRY:
            if ct.get_position() == pos:
                try_move_away(ct, pos)
            if not ct.can_build_foundry(pos):
                return False
            ct.build_foundry(pos)
            return True
        if entity == EntityType.CONVEYOR:
            if not ct.can_build_conveyor(pos, extra):
                return False
            ct.build_conveyor(pos, extra)
            return True
        if entity == EntityType.BRIDGE:
            if not ct.can_build_bridge(pos, extra):
                return False
            ct.build_bridge(pos, extra)
            return True
        return False

    def _plan_stage1(
        self,
        first_ore: Position,
        second_ore: Position,
        *,
        chain_start: tuple[int, int] | None = None,
        place_second_harvester: bool = True,
        place_first_harvester: bool = True,
        place_foundry: bool = True,
    ) -> list[BuildInstruction] | None:
        """Stage 1: harvester(second_ore) + chain(first_offset→second_offset)
        + harvester(first_ore) + foundry(first_offset). Sets self.first_offset.
        """
        # Reserve the ore tiles for this plan attempt — they'll become
        # harvesters and shouldn't be routed through. Soft block, cleared
        # by the next clear_blocked() call so it doesn't leak across plans.
        self.chain.block(first_ore.x, first_ore.y)
        self.chain.block(second_ore.x, second_ore.y)

        first_xy = (first_ore.x, first_ore.y)
        second_xy = (second_ore.x, second_ore.y)
        first_offset = self.chain.ore_offset(first_xy, second_xy)
        if first_offset is None:
            print("stage 1 first_offset is None")
            return None
        
        self.chain.set_starts([first_offset])
        if chain_start is not None:
            self.chain.set_goal(*chain_start)
        else:
            second_offset = self.chain.ore_offset(second_xy, first_offset)
            self.chain.set_goal(*(second_offset if second_offset is not None else second_xy))
        chain = self.chain.plan()
        if chain is None:
            print("stage 1 chain is None")
            return None

        plan = chain
        if place_second_harvester:
            plan.insert(0, (EntityType.HARVESTER, second_ore, None))
        if place_first_harvester:
            plan.append((EntityType.HARVESTER, first_ore, None))
        if place_foundry:
            plan.append((EntityType.FOUNDRY, Position(*first_offset), None))

        self.first_offset = first_offset
        return plan

    def _plan_stage2(
        self, first_ore: Position, goal_xy: tuple[int, int]
    ) -> list[BuildInstruction] | None:
        """Stage 2: chain from core neighbors to `goal_xy`. Blocks the 4
        cardinal neighbors of `first_ore` so the chain doesn't crowd the
        foundry / harvester adjacency.
        """
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            self.chain.block(first_ore.x + dx, first_ore.y + dy)
        cx, cy = self.core_pos.x, self.core_pos.y
        self.chain.set_starts(
            (cx + dx, cy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
        )
        self.chain.set_goal(*goal_xy)
        return self.chain.plan()

    def _chain_plan_from(
        self,
        ct: Controller,
        first_ore: Position,
        second_ore: Position,
        chain_start: tuple[int, int] | None  = None,
        *,
        place_second_harvester: bool = True,
        place_first_harvester: bool = True,
        place_foundry: bool = True,
    ) -> list[BuildInstruction] | None:
        """Plan a fresh chain: stage1 (harvesters+foundry+chain) then stage2
        (core→foundry chain). `place_*` flags omit terminals already
        present in an executed prefix.
        """
        self.chain.clear_blocked()
        stage1 = self._plan_stage1(
            first_ore,
            second_ore,
            chain_start=chain_start,
            place_second_harvester=place_second_harvester,
            place_first_harvester=place_first_harvester,
            place_foundry=place_foundry,
        )
        if stage1 is None:
            return None

        # Block every stage 1 tile so stage 2 cannot reuse it.
        for _entity, p, _extra in stage1:
            self.chain.block(p.x, p.y)

        cx, cy = self.core_pos.x, self.core_pos.y
        foundry_offset = self.chain.ore_offset(self.first_offset, (cx, cy))
        if foundry_offset is None:
            return None
        stage2 = self._plan_stage2(first_ore, foundry_offset)
        if stage2 is None:
            return None

        self._stage2_start = len(stage1)
        return stage1 + stage2

    def _pick_alt_ore(
        self, env: Environment, exclude: Position
    ) -> Position | None:
        """Pick an ore tile of `env` from the tracker, excluding `exclude`.
        env_tracker has already filtered out tiles blocked by non-buildable
        buildings. Returns the candidate closest to the core.
        """
        tracker = self.ti_ore if env == Environment.ORE_TITANIUM else self.ax_ore
        candidates = [p for p in tracker.as_positions() if p != exclude]
        if not candidates:
            return None
        cx, cy = self.core_pos.x, self.core_pos.y
        return min(
            candidates, key=lambda p: abs(p.x - cx) + abs(p.y - cy)
        )

    def _replan(self, ct: Controller, fail_idx: int) -> None:
        """Re-plan from the failure point. If we've already entered stage 2,
        only stage 2 is replanned; otherwise stage 1 (skipping anything
        already placed) followed by a fresh stage 2.
        """

        print(f"replanning {fail_idx}")

        # Drop any per-plan blocks left over from prior planning sessions
        # so this attempt sees a clean slate.
        self.chain.clear_blocked()

        plan_idx = self._plan_progress + fail_idx

        destroy_prefix: list[BuildInstruction] = []
        cut_chain = plan_idx > 0 and fail_idx == 0
        if cut_chain:
            _pe, prev_pos, _px = self._chain_plan[plan_idx - 1]
            destroy_prefix = [(EntityType.CORE, prev_pos, None)]

        if self.first_ore_pos is None:
            self._chain_plan = None
            self._plan_progress = 0
            return

        # Derive the foundry tile and the second-ore position from the
        # plan. Both appear somewhere in the full plan (including the
        # executed prefix). Stage-2 goal (foundry_offset) is recomputed
        # from the foundry tile via ore_offset at use site.
        foundry_pos: Position | None = None
        second_ore_pos: Position | None = None
        for entity, p, _x in self._chain_plan:
            if entity == EntityType.FOUNDRY:
                foundry_pos = p
            elif entity == EntityType.HARVESTER and p != self.first_ore_pos:
                second_ore_pos = p

        cur = self._plan_progress
        fail_entity, fail_pos, _x = self._chain_plan[plan_idx]
        _, chain_start_pos, _x = self._chain_plan[cur]
        chain_start = (prev_pos.x, prev_pos.y) if cut_chain else (chain_start_pos.x, chain_start_pos.y)
        in_stage2 = cur >= self._stage2_start

        print(
            f"replan fail_entity={fail_entity.name if fail_entity else None} "
            f"chain_start={chain_start} fail_pos={fail_pos}"
            f"stage2_start={self._stage2_start} "
            f"in_stage2={in_stage2} first_ore={self.first_ore_pos} "
            f"second_ore={second_ore_pos} foundry_pos={foundry_pos} "
            f"destroy_prefix={destroy_prefix}"
        )

        # Special handling: a HARVESTER or FOUNDRY tile is blocked. We need
        # to change targets, not just reroute the chain.
        if fail_entity == EntityType.FOUNDRY:
            print(f"replan FOUNDRY fail at {fail_pos}; walling and retrying offset")
            self.chain.update_tile(
                fail_pos.x, fail_pos.y, Environment.WALL, None, True
            )
            cx, cy = self.core_pos.x, self.core_pos.y
            retry = self.chain.ore_offset(
                (self.first_ore_pos.x, self.first_ore_pos.y), (cx, cy)
            )
            print(f"  ore_offset retry -> {retry}")
            if retry is None:
                print("  no alternative offset; escalating to first-ore harvester fail")
                fail_entity = EntityType.HARVESTER
                fail_pos = self.first_ore_pos

        if fail_entity == EntityType.HARVESTER:
            print(f"replan HARVESTER fail at {fail_pos}; picking alternative ore")
            self.chain.update_tile(
                fail_pos.x, fail_pos.y, Environment.WALL, None, True
            )
            if fail_pos == self.first_ore_pos:
                print(
                    f"  fail is first_ore (env={self.first_ore_env.name if self.first_ore_env else None})"
                )
                new = self._pick_alt_ore(self.first_ore_env, self.first_ore_pos)
                print(f"  new first_ore -> {new}")
                if new is None:
                    print("  no alternative first_ore; abandoning plan")
                    self._chain_plan = None
                    self._plan_progress = 0
                    return
                self.first_ore_pos = new
            else:
                other_env = (
                    Environment.ORE_AXIONITE
                    if self.first_ore_env == Environment.ORE_TITANIUM
                    else Environment.ORE_TITANIUM
                )
                print(f"  fail is second_ore (env={other_env.name})")
                new = self._pick_alt_ore(other_env, fail_pos)
                print(f"  new second_ore -> {new}")
                if new is None:
                    print("  no alternative second_ore; abandoning plan")
                    self._chain_plan = None
                    self._plan_progress = 0
                    return
                second_ore_pos = new

        # Walk the executed prefix to see what stage-1 terminals are done.
        placed_second = False
        placed_first = False
        placed_foundry = False
        for entity, p, _x in self._chain_plan[:cur]:
            if entity == EntityType.HARVESTER and p == second_ore_pos:
                placed_second = True
            elif entity == EntityType.HARVESTER and p == self.first_ore_pos:
                placed_first = True
            elif entity == EntityType.FOUNDRY:
                placed_foundry = True

        print(f"placed_second {placed_second} placed_first {placed_first} placed_foundry {placed_foundry}")

        if fail_entity in (EntityType.HARVESTER, EntityType.FOUNDRY):
            if second_ore_pos is None:
                print("  second_ore_pos is None after special-case; abandoning plan")
                self._chain_plan = None
                self._plan_progress = 0
                return
            print(
                f"  full _chain_plan_from(first_ore={self.first_ore_pos}, "
                f"second_ore={second_ore_pos})"
            )
            new_plan = self._chain_plan_from(
                ct, 
                self.first_ore_pos, 
                second_ore_pos, 
                chain_start=chain_start if placed_second else None,
                place_second_harvester=not placed_second,
                place_first_harvester=not placed_first,
                place_foundry=not placed_foundry
            )
            if new_plan is None:
                print("  _chain_plan_from returned None; abandoning plan")
                self._chain_plan = None
                self._plan_progress = 0
                return
            old_stage2_start = self._stage2_start
            self._stage2_start = cur + len(destroy_prefix) + self._stage2_start
            self._chain_plan = (
                self._chain_plan[:cur] + destroy_prefix + new_plan
            )
            self._plan_progress = cur
            print(
                f"  spliced new plan: prefix_len={cur} destroy_len={len(destroy_prefix)} "
                f"new_plan_len={len(new_plan)} "
                f"new_stage2_start={self._stage2_start} (was internal={old_stage2_start})"
            )
            return

        if in_stage2:
            print(f"replanning stage 2")
            plan = self._plan_stage2(self.first_ore_pos, chain_start)
            if plan is None:
                self._chain_plan = None
                self._plan_progress = 0
                return
            # Splice: keep already-executed prefix, replace the rest.
            self._chain_plan = self._chain_plan[:cur] + destroy_prefix + plan
            self._plan_progress = cur
            return

        if second_ore_pos is None:
            self._chain_plan = None
            self._plan_progress = 0
            return

        stage1 = self._plan_stage1(
            self.first_ore_pos,
            second_ore_pos,
            chain_start=chain_start,
            place_second_harvester=not placed_second,
            place_first_harvester=not placed_first,
            place_foundry=not placed_foundry,
        )
        if stage1 is None:
            print("could not replan stage 1")
            self._chain_plan = None
            self._plan_progress = 0
            return

        for _entity, p, _extra in stage1:
            self.chain.block(p.x, p.y)
        if foundry_pos is None:
            print("could not derive foundry_pos for stage 2 replan")
            self._chain_plan = None
            self._plan_progress = 0
            return
        cx, cy = self.core_pos.x, self.core_pos.y
        foundry_offset = self.chain.ore_offset(
            (foundry_pos.x, foundry_pos.y), (cx, cy)
        )
        if foundry_offset is None:
            print("no foundry_offset for stage 2 replan")
            self._chain_plan = None
            self._plan_progress = 0
            return
        stage2 = self._plan_stage2(self.first_ore_pos, foundry_offset)
        if stage2 is None:
            print("could not replan stage 2")
            self._chain_plan = None
            self._plan_progress = 0
            return

        self._chain_plan = self._chain_plan[:cur] + destroy_prefix + stage1 + stage2
        self._stage2_start = cur + len(destroy_prefix) + len(stage1)
        self._plan_progress = cur


    def plan_ok(self, ct: Controller) -> int:
        """Return the index of the first plan entry whose tile is not
        buildable (anything other than empty, marker, or road), or -1 if
        every entry is fine (or there is no plan). Unobserved tiles are
        treated as possible.
        """
        if self._chain_plan is None:
            return 0
        i = 0
        for entity, pos, _extra in self._chain_plan[self._plan_progress:]:
            cached = self._tile_cache[pos.y * self.w + pos.x]
            if cached == UNSEEN:
                i += 1
                continue
            bt = tile_building_type(cached)
            if entity == EntityType.CORE:
                # Destroy instruction: ok unless an enemy building sits here.
                if bt is None or tile_is_allied(cached):
                    i += 1
                    continue
                return i
            if bt in _BUILDABLE:
                i += 1
                continue
            return i
        return -1

    def _handle_explore(self, ct: Controller, new_pos: Position) -> None:
        # If a friendly builder bot with a smaller entity id is visible,
        # follow it instead of exploring on our own.
        my_team = ct.get_team()
        my_id = ct.get_id()
        leader_id: int | None = None
        leader_pos: Position | None = None
        for uid in ct.get_nearby_units():
            if uid >= my_id:
                continue
            if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
                continue
            if ct.get_team(uid) != my_team:
                continue
            if leader_id is None or uid < leader_id:
                leader_id = uid
                leader_pos = ct.get_position(uid)
        if leader_pos is not None:
            self.nav.set_goal(leader_pos)
            ct.draw_indicator_line(new_pos, leader_pos, 0, 200, 200)
            return

        if self.explore.target is not None:
            ct.draw_indicator_line(new_pos, self.explore.target, 0, 128, 0)
            self.explore.draw_unvisited(ct, 255, 0, 0)
