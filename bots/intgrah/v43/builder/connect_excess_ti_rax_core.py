"""Connect Ti or RAx excess to the core.

Finds tiles with Ti or RAx excess (flow produced but not reaching the core)
and builds a conveyor/bridge chain from the excess tile to the core. Uses
the flow A* with Ax leakage banned to prevent mixing.
"""

from cambc import Controller, Direction, EntityType, Environment, Position
from flow_astar import AX, FlowAstar
from marker import TaskClaim, TaskKind
from util import TRANSPORT

from .base import BuilderBase
from .build import Action, PlaceBridge, PlaceConveyor


class ConnectExcessTiRaxCoreMixin(BuilderBase):
    def __init__(self, ct: Controller) -> None:
        super().__init__(ct)
        self._ti_flow_search: FlowAstar | None = None
        self._ti_cached_source: tuple[int, int] | None = None
        self._ti_cached_path: list[int] | None = None

    def _connect_excess_ti_rax_core(
        self,
        ct: Controller,
        pos: Position,
    ) -> tuple[Direction, Action | None] | None:
        best_tile: tuple[int, int] | None = None
        best_dist = 999999
        w = self.state.w
        f = self.state.my_flow
        for i in (
            self.state.my_harvesters | self.state.my_transport | self.state.my_foundries
        ):
            ti_ex = f.ti_excess[i]
            rax_ex = f.rax_excess[i]
            if (ti_ex > 0.01 or rax_ex > 0.01) and not self._is_claimed(
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

        idx = self.state.idx(best_tile[0], best_tile[1])
        rnd = ct.get_current_round()
        self._claim = TaskClaim(TaskKind.FIX_EXCESS, idx, rnd)
        self._debug_target = (Position(best_tile[0], best_tile[1]), 255, 0, 0)

        sx, sy = best_tile
        si = self.state.idx(sx, sy)
        ent = self.state.entity[si]

        if ent is not None:
            etype = ent[0]
            if etype in (EntityType.HARVESTER, EntityType.FOUNDRY):
                cx, cy = self.state.my_core
                start = None
                best_d = 999999
                for ddx, ddy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nx, ny = sx + ddx, sy + ddy
                    if not self.state.in_bounds(nx, ny):
                        continue
                    ni = self.state.idx(nx, ny)
                    env = self.state.env[ni]
                    if env in (
                        Environment.WALL,
                        Environment.ORE_TITANIUM,
                        Environment.ORE_AXIONITE,
                    ):
                        continue
                    nent = self.state.entity[ni]
                    if nent is not None and nent[0] in TRANSPORT:
                        continue
                    d = (nx - cx) ** 2 + (ny - cy) ** 2
                    if d < best_d:
                        best_d = d
                        start = (nx, ny)
                if start is None:
                    return None
                sx, sy = start
            elif etype in TRANSPORT:
                d = self.state.direction[si]
                bt = self.state.bridge_target[si]
                if d is not None:
                    ddx, ddy = d.delta()
                    ox, oy = sx + ddx, sy + ddy
                    if self.state.in_bounds(ox, oy):
                        sx, sy = ox, oy
                elif bt is not None:
                    sx, sy = bt

        start = (sx, sy)
        path = self._ti_cached_path
        if path is None or self._ti_cached_source != start:
            if self._ti_flow_search is None or self._ti_cached_source != start:
                self._ti_flow_search = FlowAstar(
                    self.state,
                    sx,
                    sy,
                    self.state.my_core_tiles,
                    AX,
                )
                self._ti_cached_source = start
            self._ti_flow_search.set_budget(ct, 1200)
            self._ti_flow_search.compute()
            path = self._ti_flow_search.get_path()
            if self._ti_flow_search.done:
                self._ti_flow_search = None
            self._ti_cached_path = path
        if path is None or len(path) < 2:
            self._ti_cached_path = None
            return None

        for k in range(len(path) - 1):
            x, y = path[k] % w, path[k] // w
            nx, ny = path[k + 1] % w, path[k + 1] // w

            pi = path[k]
            pent = self.state.entity[pi]
            if pent is not None and pent[1] == self.state.my_team:
                ptype = pent[0]
                if ptype == EntityType.CORE:
                    continue
                if ptype in TRANSPORT:
                    td = self.state.direction[pi]
                    bt = self.state.bridge_target[pi]
                    if td is not None:
                        ddx, ddy = td.delta()
                        if (x + ddx, y + ddy) == (nx, ny):
                            continue
                    elif bt is not None and bt == (nx, ny):
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
