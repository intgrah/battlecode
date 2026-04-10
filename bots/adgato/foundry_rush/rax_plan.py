"""Refined-axionite chain planner: stage1 (harvesters+foundry+chain) and
stage2 (core→foundry chain), plus replanning when tiles get blocked.
"""

from __future__ import annotations

from astar import BuildInstruction, ChainAstar
from cambc import Controller, EntityType, Environment, Position, Direction
from env_tracker import EnvTracker
from tile_codec import (
    UNSEEN,
    ENV_WALL,
    ENV_AX_ORE,
    tile_building_type,
    tile_env,
    tile_is_allied,
)
from utils import try_move_away

_CARDINAL = ((1, 0), (-1, 0), (0, 1), (0, -1))

_BUILDABLE = frozenset((EntityType.ROAD, EntityType.MARKER, None))


class RaxPlan:
    def __init__(
        self,
        w: int,
        h: int,
        tile_cache: list[int],
        ti_ore: EnvTracker,
        ax_ore: EnvTracker,
    ) -> None:
        self.w = w
        self.h = h
        self._tile_cache = tile_cache
        self.ti_ore = ti_ore
        self.ax_ore = ax_ore
        self.chain = ChainAstar(w, h)
        self.core_pos: Position | None = None
        self._chain_plan: list[BuildInstruction] | None = None
        self._plan_progress: int = 0
        self._stage2_start: int = 0
        self.first_ore_pos: Position | None = None
        self.first_ore_env: Environment | None = None
        self.plan_done: bool = False
        self.first_offset: tuple[int, int] | None = None

    @property
    def has_plan(self) -> bool:
        return self._chain_plan is not None

    @property
    def plan_list(self) -> list[BuildInstruction] | None:
        return self._chain_plan

    @property
    def plan_progress(self) -> int:
        return self._plan_progress

    def set_core(self, core_pos: Position) -> None:
        self.core_pos = core_pos
        self.chain.update_tile(
            core_pos.x,
            core_pos.y,
            Environment.EMPTY,
            EntityType.CORE,
            True,
            force_update=True,
        )

    def set_first_ore(self, pos: Position, env: Environment) -> None:
        self.first_ore_pos = pos
        self.first_ore_env = env

    def begin_plan(
        self, ct: Controller, first_ore: Position, second_ore: Position
    ) -> Position | None:
        """Build a fresh plan from first→second ore. Returns the next nav goal."""
        self._chain_plan = self._chain_plan_from(ct, first_ore, second_ore)
        self._plan_progress = 0
        if self._chain_plan:
            _, gpos, _ = self._chain_plan[0]
            return gpos
        return None

    def execute(self, ct: Controller) -> Position | None:
        """Try to place the next instruction. Returns the next nav goal,
        or None if the plan completed (sets plan_done) or there's no plan.
        """
        assert self._chain_plan is not None
        entity, pos, extra = self._chain_plan[self._plan_progress]

        if self._try_place(ct, entity, pos, extra):
            self._plan_progress += 1

        if self._plan_progress >= len(self._chain_plan):
            self._chain_plan = None
            self._plan_progress = 0
            self.plan_done = True
            return None

        _, pos, _ = self._chain_plan[self._plan_progress]
        return pos

    def plan_ok(self) -> int:
        """Return the index of the first plan entry whose tile is not
        buildable (anything other than empty, marker, or road), or -1 if
        every entry is fine (or there is no plan). Unobserved tiles are
        treated as possible.
        """
        if self._chain_plan is None:
            return 0
        i = 0
        for entity, pos, _extra in self._chain_plan[self._plan_progress :]:
            cached = self._tile_cache[pos.y * self.w + pos.x]
            if cached == UNSEEN:
                i += 1
                continue
            allied = tile_is_allied(cached)
            bt = tile_building_type(cached)
            if entity == EntityType.CORE:
                if bt is None or allied:
                    i += 1
                    continue
                return i
            if bt in _BUILDABLE or bt == EntityType.BARRIER and allied:
                i += 1
                continue
            return i
        return -1

    def _ensure_sides_covered(self, ct: Controller, pos: Position) -> bool:
        """Check the 4 cardinal neighbors of `pos`. If any is a seen,
        non-wall tile with no building (or only a friendly road), try to
        place a barrier on it. Returns True if all sides are covered,
        False if a barrier was placed (or needs placing) and the caller
        should wait.
        """
        w = self.w
        for dx, dy in _CARDINAL:
            nx, ny = pos.x + dx, pos.y + dy
            if not (0 <= nx < w and 0 <= ny < self.h):
                continue
            cached = self._tile_cache[ny * w + nx]
            if cached == UNSEEN:
                continue
            if tile_env(cached) == ENV_WALL:
                continue
            bt = tile_building_type(cached)
            if bt is not None and not tile_is_allied(cached):
                return True

        for dx, dy in _CARDINAL:
            nx, ny = pos.x + dx, pos.y + dy
            if not (0 <= nx < w and 0 <= ny < self.h):
                continue
            cached = self._tile_cache[ny * w + nx]
            if cached == UNSEEN:
                continue
            if tile_env(cached) == ENV_WALL:
                continue
            bt = tile_building_type(cached)
            if bt is not None:
                continue
            # Exposed side — destroy friendly road if present, then barrier.
            side = Position(nx, ny)
            if ct.can_build_road(side):
                ct.build_road(side)
            return False
        return True

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
        if cached != UNSEEN:
            if tile_is_allied(cached):
                if ct.can_destroy(pos):
                    ct.destroy(pos)
            else:
                if ct.can_fire(pos):
                    ct.fire(pos)

        if entity == EntityType.CORE:
            # Special flag: destroy whatever allied building is at pos.
            if cached == UNSEEN:
                print("can't destroy unseen")
                return False
            ttype = tile_building_type(cached)
            if ttype is not None:
                if not ct.can_destroy(pos):
                    print(f"can't destroy {ttype} allied {tile_is_allied(cached)}")
                    return False
                ct.destroy(pos)

            self._plan_progress += 1
            entity, pos, extra = self._chain_plan[self._plan_progress]

        if entity in (EntityType.HARVESTER, EntityType.FOUNDRY):
            cached_env = self._tile_cache[pos.y * self.w + pos.x]
            if (
                entity == EntityType.FOUNDRY
                or cached_env != UNSEEN
                and tile_env(cached_env) != ENV_AX_ORE
            ):
                if not self._ensure_sides_covered(ct, pos):
                    return False
            if entity == EntityType.HARVESTER:
                if ct.get_global_resources() < ct.get_harvester_cost():
                    return False
                if ct.get_position() == pos:
                    try_move_away(ct, pos)
                if not ct.can_build_harvester(pos):
                    return False
                ct.build_harvester(pos)
                return True
            # FOUNDRY
            if ct.get_global_resources() < ct.get_foundry_cost():
                return False
            if ct.get_position() == pos:
                try_move_away(ct, pos)
            if not ct.can_build_foundry(pos):
                return False
            ct.build_foundry(pos)
            return True
        if entity == EntityType.CONVEYOR:
            if not ct.can_build_conveyor(pos, extra):
                print("can't build conveyor")
                return False
            ct.build_conveyor(pos, extra)
            return True
        if entity == EntityType.BRIDGE:
            if not ct.can_build_bridge(pos, extra):
                print("can't build bridge")
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
            if second_offset is None:
                print("second offset is None")
                return None
            self.chain.set_goal(*second_offset)
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
        assert self.core_pos is not None
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
        chain_start: tuple[int, int] | None = None,
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
            print("stage 1 None")
            return None

        # Block every stage 1 tile so stage 2 cannot reuse it.
        for _entity, p, _extra in stage1:
            self.chain.block(p.x, p.y)

        assert self.core_pos is not None
        cx, cy = self.core_pos.x, self.core_pos.y
        foundry_offset = self.chain.ore_offset(self.first_offset, (cx, cy))
        if foundry_offset is None:
            print("foundry_offset None")
            return None
        stage2 = self._plan_stage2(first_ore, foundry_offset)
        if stage2 is None:
            print("stage 2 None")
            return None

        self._stage2_start = len(stage1)
        return stage1 + stage2

    def _pick_alt_ore(self, env: Environment, exclude: Position) -> Position | None:
        """Pick an ore tile of `env` from the tracker, excluding `exclude`.
        env_tracker has already filtered out tiles blocked by non-buildable
        buildings. Returns the candidate closest to the core.
        """
        tracker = self.ti_ore if env == Environment.ORE_TITANIUM else self.ax_ore
        candidates = [p for p in tracker.as_positions() if p != exclude]
        if not candidates:
            return None
        assert self.core_pos is not None
        cx, cy = self.core_pos.x, self.core_pos.y
        return min(candidates, key=lambda p: abs(p.x - cx) + abs(p.y - cy))

    def replan(self, ct: Controller, fail_idx: int) -> None:
        """Re-plan from the failure point. If we've already entered stage 2,
        only stage 2 is replanned; otherwise stage 1 (skipping anything
        already placed) followed by a fresh stage 2.
        """

        print(f"replanning {fail_idx}")

        # Drop any per-plan blocks left over from prior planning sessions
        # so this attempt sees a clean slate.
        self.chain.clear_blocked()

        assert self._chain_plan is not None
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
        chain_start = (
            (prev_pos.x, prev_pos.y)
            if cut_chain
            else (chain_start_pos.x, chain_start_pos.y)
        )
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
            self.chain.update_tile(fail_pos.x, fail_pos.y, Environment.WALL, None, True)
            assert self.core_pos is not None
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
            self.chain.update_tile(fail_pos.x, fail_pos.y, Environment.WALL, None, True)
            if fail_pos == self.first_ore_pos:
                print(
                    f"  fail is first_ore (env={self.first_ore_env.name if self.first_ore_env else None})"
                )
                assert self.first_ore_env is not None
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

        print(
            f"placed_second {placed_second} placed_first {placed_first} placed_foundry {placed_foundry}"
        )

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
                place_foundry=not placed_foundry,
            )
            if new_plan is None:
                print("  _chain_plan_from returned None; abandoning plan")
                self._chain_plan = None
                self._plan_progress = 0
                return
            old_stage2_start = self._stage2_start
            self._stage2_start = cur + len(destroy_prefix) + self._stage2_start
            self._chain_plan = self._chain_plan[:cur] + destroy_prefix + new_plan
            self._plan_progress = cur
            print(
                f"  spliced new plan: prefix_len={cur} destroy_len={len(destroy_prefix)} "
                f"new_plan_len={len(new_plan)} "
                f"new_stage2_start={self._stage2_start} (was internal={old_stage2_start})"
            )
            return

        if in_stage2:
            print("replanning stage 2")
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
        assert self.core_pos is not None
        cx, cy = self.core_pos.x, self.core_pos.y
        foundry_offset = self.chain.ore_offset((foundry_pos.x, foundry_pos.y), (cx, cy))
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
