"""Titanium chain planner: harvester on a ti-ore tile + chain from the core
to an offset tile adjacent to the ore. Simpler than the refined-axionite
plan — no foundry, no second ore, no two-stage split.
"""

from __future__ import annotations

from astar import BuildInstruction, ChainAstar
from cambc import Controller, EntityType, Environment, Position
from env_tracker import EnvTracker
from tile_codec import ENV_WALL, UNSEEN, tile_building_type, tile_env, tile_is_allied
from utils import try_move_away

_CARDINAL = ((1, 0), (-1, 0), (0, 1), (0, -1))

_BUILDABLE = frozenset((EntityType.ROAD, EntityType.MARKER, None))


class TiPlan:
    def __init__(
        self,
        w: int,
        h: int,
        tile_cache: list[int],
        chain: ChainAstar,
        ti_ore: EnvTracker,
    ) -> None:
        self.w = w
        self.h = h
        self._tile_cache = tile_cache
        self.chain = chain
        self.ti_ore = ti_ore
        self.core_pos: Position | None = None
        self._plan: list[BuildInstruction] | None = None
        self._progress: int = 0
        self.plan_done: bool = False
        self.ore_pos: Position | None = None

    @property
    def has_plan(self) -> bool:
        return self._plan is not None

    @property
    def plan_list(self) -> list[BuildInstruction] | None:
        return self._plan

    @property
    def plan_progress(self) -> int:
        return self._progress

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

    def begin_plan(self, ct: Controller, ore: Position) -> Position | None:
        """Build a plan that chains core → ore and places a harvester.
        Returns the next nav goal, or None if no plan could be built.
        """
        self._plan = self._build_plan(ore)
        self._progress = 0
        if self._plan:
            _, gp, _ = self._plan[0]
            return gp
        return None

    def _build_plan(
        self,
        ore: Position,
        *,
        chain_start: tuple[int, int] | None = None,
        place_harvester: bool = True,
    ) -> list[BuildInstruction] | None:
        """Chain from core (or `chain_start` if resuming) to an offset
        adjacent to `ore`, then place a harvester on `ore`.

        When `chain_start` is given, the chain begins from that single
        tile instead of the 3x3 core ring — used by replanning to resume
        a partially-built chain.
        """
        assert self.core_pos is not None
        self.chain.clear_blocked()
        self.chain.block(ore.x, ore.y)

        cx, cy = self.core_pos.x, self.core_pos.y

        self.chain.set_starts(
            (cx + dx, cy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
        )
        if chain_start is not None:
            self.chain.set_goal(*chain_start)
        else:
            offset = self.chain.ore_offset((ore.x, ore.y), (cx, cy))
            if offset is None:
                print("ti plan: ore_offset is None")
                return None
            self.chain.set_goal(*offset)
        chain = self.chain.plan()
        if chain is None:
            print("ti plan: chain is None")
            return None

        plan = chain
        if place_harvester:
            plan.insert(0, (EntityType.HARVESTER, ore, None))
        self.ore_pos = ore
        return plan

    def execute(self, ct: Controller) -> Position | None:
        """Try to place the next instruction. Returns the next nav goal,
        or None if the plan finished (sets plan_done).
        """
        assert self._plan is not None
        entity, pos, extra = self._plan[self._progress]

        if self._try_place(ct, entity, pos, extra):
            self._progress += 1

        if self._progress >= len(self._plan):
            self._plan = None
            self._progress = 0
            self.plan_done = True
            return None

        _, pos, _ = self._plan[self._progress]
        return pos

    def plan_ok(self) -> int:
        """Return the first plan index whose tile is not buildable, or -1
        if the whole remaining plan is fine (or there is no plan).
        """
        if self._plan is None:
            return 0
        i = 0
        for entity, pos, _extra in self._plan[self._progress :]:
            cached = self._tile_cache[pos.y * self.w + pos.x]
            if cached == UNSEEN:
                i += 1
                continue
            bt = tile_building_type(cached)
            allied = tile_is_allied(cached)
            if entity == EntityType.CORE:
                # Destroy instruction: ok unless an enemy building sits here.
                if bt is None or allied:
                    i += 1
                    continue
                return i
            if bt in _BUILDABLE or (bt == EntityType.BARRIER and allied):
                i += 1
                continue
            return i
        return -1

    def _pick_alt_ore(self, exclude: Position) -> Position | None:
        """Pick the closest-to-core ti-ore tile other than `exclude`."""
        candidates = [p for p in self.ti_ore.as_positions() if p != exclude]
        if not candidates:
            return None
        assert self.core_pos is not None
        cx, cy = self.core_pos.x, self.core_pos.y
        return min(candidates, key=lambda p: abs(p.x - cx) + abs(p.y - cy))

    def replan(self, ct: Controller, fail_idx: int) -> None:
        """Re-plan from the failure point. If the failing tile is the
        harvester target, swap to an alternative ore; otherwise resume
        the chain from whatever's already been placed.

        If `fail_idx == 0` and we've already executed some prefix, we
        prepend a destroy instruction for the last-placed tile and
        resume the chain from that tile — matching `RaxPlan`'s behavior
        so the new route can leave through the same spot.
        """
        assert self._plan is not None
        self.chain.clear_blocked()

        cur = self._progress
        plan_idx = cur + fail_idx
        fail_entity, fail_pos, _ = self._plan[plan_idx]

        destroy_prefix: list[BuildInstruction] = []
        cut_chain = plan_idx > 0 and fail_idx == 0
        prev_pos: Position | None = None
        if cut_chain:
            _pe, prev_pos, _px = self._plan[plan_idx - 1]
            destroy_prefix = [(EntityType.CORE, prev_pos, None)]

        if fail_entity == EntityType.HARVESTER:
            # Ore tile blocked — pick a different ore.
            self.chain.update_tile(fail_pos.x, fail_pos.y, Environment.WALL, None, True)
            new_ore = self._pick_alt_ore(fail_pos)
            if new_ore is None:
                self._plan = None
                self._progress = 0
                return
            chain_start = None
            if cut_chain and prev_pos is not None:
                chain_start = (prev_pos.x, prev_pos.y)
            elif cur > 0:
                _, start_pos, _ = self._plan[cur]
                chain_start = (start_pos.x, start_pos.y)
            new_plan = self._build_plan(
                new_ore, chain_start=chain_start, place_harvester=cur == 0
            )
            if new_plan is None:
                self._plan = None
                self._progress = 0
                return
            self._plan = self._plan[:cur] + destroy_prefix + new_plan
            self._progress = cur
            return

        # Chain tile blocked — resume the chain for the same ore.
        assert self.ore_pos is not None
        chain_start: tuple[int, int] | None = None
        if cut_chain and prev_pos is not None:
            chain_start = (prev_pos.x, prev_pos.y)
        elif cur > 0:
            _, start_pos, _ = self._plan[cur]
            chain_start = (start_pos.x, start_pos.y)

        # If the harvester was already placed, don't place it again.
        placed_harvester = any(
            e == EntityType.HARVESTER for e, _, _ in self._plan[:cur]
        )

        new_plan = self._build_plan(
            self.ore_pos,
            chain_start=chain_start,
            place_harvester=not placed_harvester,
        )
        if new_plan is None:
            self._plan = None
            self._progress = 0
            return
        self._plan = self._plan[:cur] + destroy_prefix + new_plan
        self._progress = cur

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
            if bt is not None and not (
                bt == EntityType.ROAD and tile_is_allied(cached)
            ):
                continue
            # Exposed side — destroy friendly road if present, then barrier.
            side = Position(nx, ny)
            if bt == EntityType.ROAD and tile_is_allied(cached):
                if ct.can_destroy(side):
                    ct.destroy(side)
                else:
                    return False
            if ct.can_build_barrier(side):
                ct.build_barrier(side)
            return False
        return True

    def _try_place(
        self,
        ct: Controller,
        entity: EntityType,
        pos: Position,
        extra: object,
    ) -> bool:
        # Clear any road sitting on the target tile first.
        cached = self._tile_cache[pos.y * self.w + pos.x]
        if cached != UNSEEN:
            if tile_is_allied(cached):
                if ct.can_destroy(pos):
                    ct.destroy(pos)
            elif ct.can_fire(pos):
                ct.fire(pos)

        if entity == EntityType.CORE:
            # Destroy whatever allied building sits at pos, then fall
            # through to the next real instruction.
            if cached == UNSEEN:
                return False
            ttype = tile_building_type(cached)
            if ttype is not None:
                if not ct.can_destroy(pos):
                    return False
                ct.destroy(pos)

            assert self._plan is not None
            self._progress += 1
            entity, pos, extra = self._plan[self._progress]

        if entity == EntityType.HARVESTER:
            if not self._ensure_sides_covered(ct, pos):
                return False
            if ct.get_global_resources() < ct.get_harvester_cost():
                return False
            if ct.get_position() == pos:
                try_move_away(ct, pos)
            if not ct.can_build_harvester(pos):
                return False
            ct.build_harvester(pos)
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
