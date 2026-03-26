import json
from typing import TYPE_CHECKING

from cambc import (
    Controller,
    Direction,
    EntityType,
    Environment,
    GameConstants,
    Position,
)
from flow_astar import build_leakage_mask
from marker import Eureka, TaskClaim

from .build import Action, PlaceRoad, Task, execute
from .connect_excess_ax_ti_conv import ConnectExcessAxTiConvMixin
from .connect_excess_ti_rax_core import ConnectExcessTiRaxCoreMixin
from .explore import ExploreMixin
from .harvest_ax import HarvestAxMixin
from .harvest_ti import HarvestTiMixin
from .nav_enemy_core import NavEnemyCoreMixin
from .patrol import PatrolMixin
from .place_foundry_mixed_conv import PlaceFoundryMixedConvMixin
from .place_foundry_ti_conv import PlaceFoundryTiConvMixin
from .place_splitter_foundry import PlaceSplitterFoundryMixin
from .raid import RaidMixin
from .state import State

if TYPE_CHECKING:
    from nav_astar import NavAstar

DEBUG_DUMP = False


class Builder(
    HarvestTiMixin,
    HarvestAxMixin,
    ConnectExcessTiRaxCoreMixin,
    ConnectExcessAxTiConvMixin,
    PlaceFoundryTiConvMixin,
    PlaceFoundryMixedConvMixin,
    PlaceSplitterFoundryMixin,
    RaidMixin,
    NavEnemyCoreMixin,
    PatrolMixin,
    ExploreMixin,
):
    def __init__(self, ct: Controller) -> None:
        super().__init__(ct)
        core_pos = self._find_core(ct)
        self.state = State(
            self.w,
            self.h,
            self.team,
            (core_pos.x, core_pos.y),
        )
        self._last_claim: TaskClaim | None = None
        self._nav_target_key: tuple[int, int] | None = None
        self._nav_path: list[int] | None = None
        self._nav_search: NavAstar | None = None

    def run(self, ct: Controller) -> None:
        _, needs_reflow = self.state.update(ct)
        if needs_reflow or not hasattr(self, "_leakage_mask"):
            self._flow_search = None
            self._cached_chain_path = None
            self._ax_flow_search = None
            self._ax_cached_path = None
            self._leakage_mask = build_leakage_mask(self.state)

        pos = ct.get_position()
        if DEBUG_DUMP:
            self._dump(ct)
        self._debug_target = None
        self._claim: TaskClaim | None = None

        move, build = self._execute(ct, pos)

        if move != Direction.CENTRE:
            if ct.can_move(move):
                ct.move(move)
            elif isinstance(build, PlaceRoad):
                execute(build, ct)
                if ct.can_move(move):
                    ct.move(move)
                build = None
        if build is not None:
            execute(build, ct)

        if self._debug_target is not None:
            ct.draw_indicator_line(ct.get_position(), *self._debug_target)
        self._write_marker(ct)

    def _dump(self, ct: Controller) -> None:
        pos = ct.get_position()
        b = self.state
        n = b.w * b.h
        data = {
            "w": b.w,
            "h": b.h,
            "round": ct.get_current_round(),
            "eid": ct.get_id(),
            "pos": [pos.x, pos.y],
            "explore_radius": self._explore_radius,
            "env": [b.env[i].value if b.env[i] is not None else None for i in range(n)],
            "entity": [
                [b.entity[i][0].value, b.entity[i][1].value]
                if b.entity[i] is not None
                else None
                for i in range(n)
            ],
            "direction": [
                b.direction[i].value if b.direction[i] is not None else None
                for i in range(n)
            ],
            "bridge_target": {
                str(i): [b.bridge_target[i][0], b.bridge_target[i][1]]
                for i in range(n)
                if b.bridge_target[i] is not None
            },
            "my_core": list(b.my_core),
            "ore_ti": list(b.ore_ti),
            "ore_ax": list(b.ore_ax),
            "my_harvesters": list(b.my_harvesters),
            "my_transport": list(b.my_transport),
            "my_foundries": list(b.my_foundries),
            "flow_ti": {
                i: round(b.my_flow.ti[i], 3)
                for i in range(n)
                if b.my_flow.ti[i] > 0.001
            },
            "flow_ax": {
                i: round(b.my_flow.ax[i], 3)
                for i in range(n)
                if b.my_flow.ax[i] > 0.001
            },
            "flow_rax": {
                i: round(b.my_flow.rax[i], 3)
                for i in range(n)
                if b.my_flow.rax[i] > 0.001
            },
            "blocked": [i for i in range(n) if b.my_flow.blocked[i]],
            "excess_ti": {
                i: round(b.my_flow.ti_excess[i], 3)
                for i in range(n)
                if b.my_flow.ti_excess[i] > 0.001
            },
            "excess_ax": {
                i: round(b.my_flow.ax_excess[i], 3)
                for i in range(n)
                if b.my_flow.ax_excess[i] > 0.001
            },
            "excess_rax": {
                i: round(b.my_flow.rax_excess[i], 3)
                for i in range(n)
                if b.my_flow.rax_excess[i] > 0.001
            },
            "leakage": {
                i: self._leakage_mask[i] for i in range(n) if self._leakage_mask[i] != 0
            },
            "unit_tiles": list(b.unit_tiles),
            "symmetry": b.symmetry.name if b.symmetry is not None else None,
        }
        print("BELIEF:" + json.dumps(data, separators=(",", ":")))

    def _policy(self, pos: Position) -> list[tuple[float, Task]]:
        """Score each task. Higher = more priority."""
        scores: list[tuple[float, Task]] = []

        has_excess = any(
            self.state.my_flow.excess[i] > 0.01
            for i in self.state.my_harvesters | self.state.my_transport
        )
        scores.append((100.0 if has_excess else 0.0, Task.CONNECT_EXCESS_TI_RAX_CORE))

        unharvested_ti = (
            self.state.ore_ti - self.state.my_harvested - self.state.en_harvested
        )
        if unharvested_ti:
            nearest_ti_dist = min(
                abs(pos.x - ox) + abs(pos.y - oy) for ox, oy in unharvested_ti
            )
            scores.append((max(1.0, 50.0 - nearest_ti_dist), Task.HARVEST_TI))
        else:
            scores.append((0.0, Task.HARVEST_TI))

        unharvested_ax = (
            self.state.ore_ax - self.state.my_harvested - self.state.en_harvested
        )
        if unharvested_ax:
            nearest_ax_dist = min(
                abs(pos.x - ox) + abs(pos.y - oy) for ox, oy in unharvested_ax
            )
            scores.append((max(1.0, 50.0 - nearest_ax_dist), Task.HARVEST_AX))
        else:
            scores.append((0.0, Task.HARVEST_AX))

        has_mixed_conv = any(
            self.state.my_flow.ti[i] > 0
            and self.state.my_flow.ax[i] > 0
            and self.state.entity[i] is not None
            and self.state.entity[i][0]
            in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR)
            for i in self.state.my_transport
        )
        scores.append((90.0 if has_mixed_conv else 0.0, Task.PLACE_FOUNDRY_MIXED_CONV))

        has_foundry_no_splitter = bool(self.state.my_foundries) and any(
            self.state.entity[ni] is not None
            and self.state.entity[ni][0]
            in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR)
            and self.state.entity[ni][1] == self.state.my_team
            for fi in self.state.my_foundries
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]
            if self.state.in_bounds(
                (
                    ni := self.state.idx(
                        (fi % self.state.w) + dx,
                        (fi // self.state.w) + dy,
                    )
                )
                % self.state.w,
                ni // self.state.w,
            )
        )
        scores.append(
            (85.0 if has_foundry_no_splitter else 0.0, Task.PLACE_SPLITTER_FOUNDRY),
        )

        scores.append((0.0, Task.CONNECT_EXCESS_AX_TI_CONV))
        scores.append((20.0, Task.EXPLORE))
        scores.append((5.0, Task.PATROL))
        scores.append((0.0, Task.NAV_ENEMY_CORE))
        scores.append((0.0, Task.RAID))

        scores.sort(key=lambda t: t[0], reverse=True)
        return scores

    def _execute(
        self,
        ct: Controller,
        pos: Position,
    ) -> tuple[Direction, Action | None]:
        for _, task in self._policy(pos):
            match task:
                case Task.CONNECT_EXCESS_TI_RAX_CORE:
                    result = self._connect_excess_ti_rax_core(ct, pos)
                case Task.HARVEST_TI:
                    result = self._harvest_ti(ct, pos)
                case Task.HARVEST_AX:
                    result = self._harvest_ax(ct, pos)
                case Task.RAID:
                    result = self._raid(ct, pos)
                case Task.EXPLORE:
                    result = self._explore(ct, pos)
                case Task.PATROL:
                    result = self._patrol(ct, pos)
                case Task.NAV_ENEMY_CORE:
                    result = self._nav_enemy_core(ct, pos)
                case Task.PLACE_FOUNDRY_MIXED_CONV:
                    result = self._place_foundry_mixed_conv(ct, pos)
                case Task.PLACE_SPLITTER_FOUNDRY:
                    result = self._place_splitter_foundry(ct, pos)
                case Task.CONNECT_EXCESS_AX_TI_CONV:
                    result = self._connect_excess_ax_ti_conv(ct, pos)
                case _:
                    result = None
            if result is not None:
                return result
        return Direction.CENTRE, None

    def _write_marker(self, ct: Controller) -> None:
        marker_val = None
        if self._claim is not None:
            self._last_claim = self._claim
            marker_val = self._claim.encode()
        elif self.state.symmetry is not None:
            marker_val = Eureka(self.state.symmetry.value).encode()
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
            if (
                bid is not None
                and ct.get_entity_type(bid) == EntityType.MARKER
                and ct.get_team(bid) == ct.get_team()
            ):
                ct.destroy(t)
                ct.place_marker(t, marker_val)
                return

    def _find_core(self, ct: Controller) -> Position:
        my = ct.get_team()
        for bid in ct.get_nearby_buildings():
            if ct.get_team(bid) == my and ct.get_entity_type(bid) == EntityType.CORE:
                return ct.get_position(bid)
        raise RuntimeError
