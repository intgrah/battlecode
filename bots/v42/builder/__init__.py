import time

from cambc import (
    Controller,
    Direction,
    EntityType,
    Environment,
    GameConstants,
    Position,
)
from flow_astar import build_leakage_mask
from map_belief import MapBelief
from marker import Eureka, TaskClaim

from .build import Build, BuildKind
from .explore import ExploreMixin
from .fix_excess import FixExcessMixin
from .foundry import FoundryMixin
from .harvest import HarvestMixin
from .raid import RaidMixin


class Builder(HarvestMixin, FixExcessMixin, FoundryMixin, RaidMixin, ExploreMixin):
    def __init__(self, ct: Controller) -> None:
        super().__init__(ct)
        core_pos = self._find_core(ct)
        self.belief = MapBelief(
            self.w,
            self.h,
            self.team,
            (core_pos.x, core_pos.y),
        )
        self._last_claim: TaskClaim | None = None

    def run(self, ct: Controller) -> None:

        t0 = time.perf_counter_ns()
        _, needs_reflow = self.belief.update(ct)
        if needs_reflow:
            self._flow_search = None
            self._cached_chain_path = None
            self._ax_flow_search = None
            self._ax_cached_path = None
            self._leakage_mask = build_leakage_mask(self.belief)
        t1 = time.perf_counter_ns()

        pos = ct.get_position()
        self._debug_target = None
        self._claim: TaskClaim | None = None

        move, build = self._policy(ct, pos)
        t2 = time.perf_counter_ns()
        if not hasattr(self, "_tlog"):
            self._tlog = open("/tmp/v42_cpu.log", "w")
        self._tlog.write(
            f"{ct.get_current_round()} {(t1 - t0) // 1000} {(t2 - t1) // 1000}\n",
        )

        if move != Direction.CENTRE:
            if ct.can_move(move):
                ct.move(move)
            elif build is not None and build.kind == BuildKind.ROAD:
                build.execute(ct)
                if ct.can_move(move):
                    ct.move(move)
                build = None
        if build is not None:
            build.execute(ct)

        if self._debug_target is not None:
            ct.draw_indicator_line(ct.get_position(), *self._debug_target)
        self._write_marker(ct)

    def _policy(self, ct: Controller, pos: Position) -> tuple[Direction, Build | None]:
        tasks = [
            ("fix_ti", self._fix_excess_ti_rax),
            ("foundry", self._place_foundry),
            ("fix_ax", self._fix_excess_ax),
            ("harv_ti", self._harvest_ti),
            ("harv_ax", self._harvest_ax),
            ("raid", self._raid),
            ("explore", self._explore),
        ]
        if not hasattr(self, "_plog"):
            self._plog = open("/tmp/v42_pol.log", "w")
        parts = []
        for name, fn in tasks:
            t0 = time.perf_counter_ns()
            result = fn(ct, pos)
            t1 = time.perf_counter_ns()
            parts.append(f"{name}={(t1 - t0) // 1000}")
            if result is not None:
                self._plog.write(
                    f"{ct.get_current_round()} {' '.join(parts)} -> {name}\n",
                )
                return result
        self._plog.write(f"{ct.get_current_round()} {' '.join(parts)} -> idle\n")
        result = None
        if result is not None:
            return result

        return Direction.CENTRE, None

    def _write_marker(self, ct: Controller) -> None:
        marker_val = None
        if self._claim is not None:
            self._last_claim = self._claim
            marker_val = self._claim.encode()
        elif self.belief.symmetry is not None:
            marker_val = Eureka(self.belief.symmetry.value).encode()
        if marker_val is None:
            return
        pos = ct.get_position()
        for t in ct.get_nearby_tiles(GameConstants.ACTION_RADIUS_SQ):
            if t == pos:
                continue
            env = ct.get_tile_env(t)
            if env in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE):
                continue
            if ct.can_place_marker(t):
                ct.place_marker(t, marker_val)
                return
        for t in ct.get_nearby_tiles(GameConstants.ACTION_RADIUS_SQ):
            if t == pos:
                continue
            bid = ct.get_tile_building_id(t)
            if bid is not None and ct.get_entity_type(bid) == EntityType.MARKER:
                ct.destroy(t)
                ct.place_marker(t, marker_val)
                return

    def _find_core(self, ct: Controller) -> Position:
        my = ct.get_team()
        for bid in ct.get_nearby_buildings():
            if ct.get_team(bid) == my and ct.get_entity_type(bid) == EntityType.CORE:
                return ct.get_position(bid)
        raise RuntimeError
