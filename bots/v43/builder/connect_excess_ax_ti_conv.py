"""Connect Ax excess to the nearest Ti conveyor with flow.

Finds Ax harvesters with excess and builds a chain of conveyors from the
harvester to the nearest Ti conveyor carrying Ti flow. This creates mixed
Ti+Ax flow at the junction, which triggers the place_foundry task.

Uses the Ax chain A* with Ti and RAx leakage banned to ensure the Ax chain
stays pure.
"""

from ax_chain_astar import AxChainAstar
from cambc import Controller, Direction, EntityType, Environment, Position
from flow_astar import RAX, TI
from map_belief import _TRANSPORT
from marker import TaskClaim, TaskKind

from .base import BuilderBase
from .build import Action, PlaceBridge, PlaceConveyor


class ConnectExcessAxTiConvMixin(BuilderBase):
    def __init__(self, ct: Controller) -> None:
        super().__init__(ct)
        self._ax_flow_search: AxChainAstar | None = None
        self._ax_cached_source: tuple[int, int] | None = None
        self._ax_cached_path: list[int] | None = None

    def _connect_excess_ax_ti_conv(
        self,
        ct: Controller,
        pos: Position,
    ) -> tuple[Direction, Action | None] | None:
        best_tile: tuple[int, int] | None = None
        best_dist = 999999
        w = self.belief.w
        f = self.belief.my_flow
        for i in self.belief.my_harvesters | self.belief.my_transport:
            if f.ax_excess[i] > 0.01 and not self._is_claimed(
                i,
                TaskKind.FIX_EXCESS,
            ):
                x, y = i % w, i // w
                dist = (pos.x - x) ** 2 + (pos.y - y) ** 2
                if dist < best_dist:
                    best_dist = dist
                    best_tile = (x, y)
        if best_tile is None:
            return None

        ti_goals = self._find_ti_conveyor_goals()
        if not ti_goals:
            return None

        ti_idx = self.belief.idx(best_tile[0], best_tile[1])
        rnd = ct.get_current_round()
        self._claim = TaskClaim(TaskKind.FIX_EXCESS, ti_idx, rnd)
        self._debug_target = (Position(best_tile[0], best_tile[1]), 255, 0, 255)

        sx, sy = best_tile
        si = self.belief.idx(sx, sy)
        ent = self.belief.entity[si]
        if ent is not None and ent[0] in (EntityType.HARVESTER, EntityType.FOUNDRY):
            banned = TI | RAX
            start = None
            for ddx, ddy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx, ny = sx + ddx, sy + ddy
                if not self.belief.in_bounds(nx, ny):
                    continue
                ni = self.belief.idx(nx, ny)
                env = self.belief.env[ni]
                if env in (
                    Environment.WALL,
                    Environment.ORE_TITANIUM,
                    Environment.ORE_AXIONITE,
                ):
                    continue
                nent = self.belief.entity[ni]
                if nent is not None and nent[0] in _TRANSPORT:
                    continue
                if self._leakage_mask[ni] & banned != 0:
                    continue
                start = (nx, ny)
                break
            if start is None:
                return None
            sx, sy = start

        start = (sx, sy)
        path = self._ax_cached_path
        if path is None or self._ax_cached_source != start:
            if self._ax_flow_search is None or self._ax_cached_source != start:
                self._ax_flow_search = AxChainAstar(
                    self.belief,
                    sx,
                    sy,
                    ti_goals,
                )
                self._ax_cached_source = start
            self._ax_flow_search.set_budget(ct, 1200)
            self._ax_flow_search.compute()
            path = self._ax_flow_search.get_path()
            if self._ax_flow_search.done:
                self._ax_flow_search = None
            self._ax_cached_path = path
        if path is None or len(path) < 2:
            self._ax_cached_path = None
            return None

        banned = TI | RAX
        for k in range(len(path) - 1):
            x, y = path[k] % w, path[k] // w
            nx, ny = path[k + 1] % w, path[k + 1] // w

            pi = path[k]
            pent = self.belief.entity[pi]
            if pent is not None and pent[1] == self.belief.my_team:
                ptype = pent[0]
                if ptype in _TRANSPORT or ptype == EntityType.CORE:
                    continue

            build_at = Position(x, y)
            dx, dy = nx - x, ny - y
            is_cardinal = abs(dx) + abs(dy) == 1

            if pos == build_at:
                adj = self._cardinal_adjacent(pos, build_at)
                if adj is not None:
                    return self._move_toward_with_road(ct, pos, adj)
                continue

            if is_cardinal:
                if pos.distance_squared(build_at) <= 2:
                    d = build_at.direction_to(Position(nx, ny))
                    return Direction.CENTRE, PlaceConveyor(build_at, d)
                adj = self._cardinal_adjacent(pos, build_at)
                if adj is not None:
                    return self._move_toward_with_road(ct, pos, adj)
                continue

            if pos.distance_squared(build_at) <= 2:
                return Direction.CENTRE, PlaceBridge(build_at, Position(nx, ny))
            adj = self._cardinal_adjacent(pos, build_at)
            if adj is not None:
                return self._move_toward_with_road(ct, pos, adj)

        return None

    def _find_ti_conveyor_goals(self) -> set[int]:
        f = self.belief.my_flow
        goals: set[int] = set()
        for i in self.belief.my_transport:
            if f.ti[i] <= 0:
                continue
            ent = self.belief.entity[i]
            if ent is None:
                continue
            if ent[0] in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR):
                goals.add(i)
        return goals
