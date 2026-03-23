from cambc import Controller, Direction, EntityType, Environment, Position
from flow_astar import FlowAstar, flow_astar
from map_belief import _TRANSPORT
from marker import TaskClaim, TaskKind

from .base import BuilderBase
from .build import Build, BuildKind


class FixExcessMixin(BuilderBase):
    def __init__(self, ct: Controller) -> None:
        super().__init__(ct)
        self._flow_search: FlowAstar | None = None
        self._cached_chain_source: tuple[int, int] | None = None
        self._cached_chain_path: list[tuple[int, int]] | None = None

    def _fix_excess(
        self,
        ct: Controller,
        pos: Position,
    ) -> tuple[Direction, Build | None] | None:
        best_tile = None
        best_dist = 999999
        w = self.belief.w
        for i in self.belief.my_harvesters | self.belief.my_transport | self.belief.my_foundries:
            if self.belief.my_flow.excess[i] > 0.01 and not self._is_claimed(
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
        ti = self.belief.idx(best_tile[0], best_tile[1])
        rnd = ct.get_current_round()
        self._claim = TaskClaim(TaskKind.FIX_EXCESS, ti, rnd)
        self._debug_target = (Position(best_tile[0], best_tile[1]), 255, 0, 0)
        result = self._build_chain(ct, pos, best_tile)
        with open("/tmp/v41_flow_debug.log", "a") as dbg:
            dbg.write(f"  fix_excess target=({best_tile[0]},{best_tile[1]}) chain_result={result is not None}\n")
        return result

    def _build_chain(
        self,
        ct: Controller,
        pos: Position,
        source: tuple[int, int],
    ) -> tuple[Direction, Build | None] | None:
        cx, cy = self.belief.my_core
        sx, sy = source

        si = self.belief.idx(sx, sy)
        ent = self.belief.entity[si]

        if ent is not None:
            etype = ent[0]
            if etype in (EntityType.HARVESTER, EntityType.FOUNDRY):
                best_start = None
                best_d = 999999
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
                    d = (nx - cx) ** 2 + (ny - cy) ** 2
                    if d < best_d:
                        best_d = d
                        best_start = (nx, ny)
                if best_start is None:
                    return None
                sx, sy = best_start
            elif etype in _TRANSPORT:
                d = self.belief.direction[si]
                bt = self.belief.bridge_target[si]
                if d is not None:
                    dx, dy = d.delta()
                    ox, oy = sx + dx, sy + dy
                    if self.belief.in_bounds(ox, oy):
                        sx, sy = ox, oy
                elif bt is not None:
                    sx, sy = bt

        start = (sx, sy)
        with open("/tmp/v41_flow_debug.log", "a") as dbg:
            dbg.write(f"  chain start=({sx},{sy}) source=({source[0]},{source[1]})\n")
        path = self._cached_chain_path
        if path is None or self._cached_chain_source != start:
            if self._flow_search is None or self._cached_chain_source != start:
                self._flow_search = flow_astar(
                    self.belief,
                    sx,
                    sy,
                    *self.belief.my_core,
                )
                self._cached_chain_source = start
            self._flow_search.compute(ct, 1200)
            path = self._flow_search.get_path()
            if self._flow_search.done:
                self._flow_search = None
            self._cached_chain_path = path
        if path is None or len(path) < 2:
            self._cached_chain_path = None
            with open("/tmp/v41_flow_debug.log", "a") as dbg:
                dbg.write(f"  chain FAILED path={path} done={self._flow_search is None}\n")
            return None

        for k in range(len(path) - 1):
            x, y = path[k]
            nx, ny = path[k + 1]

            pi = self.belief.idx(x, y)
            pent = self.belief.entity[pi]
            if pent is not None and pent[1] == self.belief.my_team:
                ptype = pent[0]
                if ptype == EntityType.CORE:
                    continue
                if ptype in _TRANSPORT:
                    d = self.belief.direction[pi]
                    bt = self.belief.bridge_target[pi]
                    if d is not None:
                        ddx, ddy = d.delta()
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
                    move, road = self._move_toward_with_road(ct, pos, adj)
                    return move, road
                continue

            if is_cardinal:
                if pos.distance_squared(build_at) <= 2:
                    d = build_at.direction_to(Position(nx, ny))
                    return Direction.CENTRE, Build(BuildKind.CONVEYOR, build_at, d)
                adj = self._cardinal_adjacent(pos, build_at)
                if adj is not None:
                    move, road = self._move_toward_with_road(ct, pos, adj)
                    return move, road
                continue

            if pos.distance_squared(build_at) <= 2:
                return Direction.CENTRE, Build(
                    BuildKind.BRIDGE,
                    build_at,
                    Position(nx, ny),
                )
            adj = self._cardinal_adjacent(pos, build_at)
            if adj is not None:
                move, road = self._move_toward_with_road(ct, pos, adj)
                return move, road

        return None
