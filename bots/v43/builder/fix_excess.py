from cambc import Controller, Direction, EntityType, Environment, Position
from flow_astar import AX, RAX, TI, Astar, flow_astar
from map_belief import _TRANSPORT
from marker import TaskClaim, TaskKind

from .base import BuilderBase
from .build import Build, BuildKind


class FixExcessMixin(BuilderBase):
    def __init__(self, ct: Controller) -> None:
        super().__init__(ct)
        self._flow_search: Astar | None = None
        self._cached_chain_source: tuple[int, int] | None = None
        self._cached_chain_path: list[tuple[int, int]] | None = None

    def _commodity_of(self, i: int) -> int:
        f = self.belief.my_flow
        c = 0
        if f.ti_excess[i] > 0.01 or f.ti[i] > 0:
            c |= TI
        if f.ax_excess[i] > 0.01 or f.ax[i] > 0:
            c |= AX
        if f.rax_excess[i] > 0.01 or f.rax[i] > 0:
            c |= RAX
        return c

    def _fix_excess_ti_rax(
        self,
        ct: Controller,
        pos: Position,
    ) -> tuple[Direction, Build | None] | None:
        best_tile = None
        best_dist = 999999
        w = self.belief.w
        f = self.belief.my_flow
        for i in (
            self.belief.my_harvesters
            | self.belief.my_transport
            | self.belief.my_foundries
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
        idx = self.belief.idx(best_tile[0], best_tile[1])
        rnd = ct.get_current_round()
        self._claim = TaskClaim(TaskKind.FIX_EXCESS, idx, rnd)
        self._debug_target = (Position(best_tile[0], best_tile[1]), 255, 0, 0)
        allowed = self._commodity_of(idx)
        return self._build_chain_to_core(
            ct, pos, best_tile, banned_leakage=(TI | AX | RAX) & ~allowed
        )

    def _fix_excess_ax(
        self,
        ct: Controller,
        pos: Position,
    ) -> tuple[Direction, Build | None] | None:
        best_tile = None
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
        ti_idx = self.belief.idx(best_tile[0], best_tile[1])
        rnd = ct.get_current_round()
        self._claim = TaskClaim(TaskKind.FIX_EXCESS, ti_idx, rnd)
        self._debug_target = (Position(best_tile[0], best_tile[1]), 255, 0, 255)

        target = self._find_ti_conveyor(best_tile)
        if target is None:
            return None
        return self._build_ax_chain(ct, pos, best_tile, target)

    def _find_ti_conveyor(self, source: tuple[int, int]) -> tuple[int, int] | None:
        best_conv = None
        best_dist = 999999
        w = self.belief.w
        f = self.belief.my_flow
        for i in self.belief.my_transport:
            if f.ti[i] <= 0:
                continue
            ent = self.belief.entity[i]
            if ent is None:
                continue
            if ent[0] not in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR):
                continue
            x, y = i % w, i // w
            dist = (source[0] - x) ** 2 + (source[1] - y) ** 2
            if dist < best_dist:
                best_dist = dist
                best_conv = (x, y)
        return best_conv

    def _build_ax_chain(
        self,
        ct: Controller,
        pos: Position,
        source: tuple[int, int],
        target: tuple[int, int],
    ) -> tuple[Direction, Build | None] | None:
        sx, sy = source
        si = self.belief.idx(sx, sy)
        ent = self.belief.entity[si]
        if ent is not None and ent[0] in (EntityType.HARVESTER, EntityType.FOUNDRY):
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
                d = (nx - target[0]) ** 2 + (ny - target[1]) ** 2
                if d < best_d:
                    best_d = d
                    best_start = (nx, ny)
            if best_start is None:
                return None
            sx, sy = best_start

        gx, gy = target
        gi = self.belief.idx(gx, gy)
        search = flow_astar(
            self.belief,
            sx,
            sy,
            gx,
            gy,
            goal_set={gi},
            banned_leakage=TI | RAX,
        )
        search.compute(ct, 1200)
        path = search.get_path()
        if path is None or len(path) < 2:
            return None

        for k in range(len(path) - 1):
            x, y = path[k]
            nx, ny = path[k + 1]

            pi = self.belief.idx(x, y)
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
                    return Direction.CENTRE, Build(BuildKind.CONVEYOR, build_at, d)
                adj = self._cardinal_adjacent(pos, build_at)
                if adj is not None:
                    return self._move_toward_with_road(ct, pos, adj)
                continue

            if pos.distance_squared(build_at) <= 2:
                return Direction.CENTRE, Build(
                    BuildKind.BRIDGE,
                    build_at,
                    Position(nx, ny),
                )
            adj = self._cardinal_adjacent(pos, build_at)
            if adj is not None:
                return self._move_toward_with_road(ct, pos, adj)

        return None

    def _build_chain_to_target(
        self,
        ct: Controller,
        pos: Position,
        source: tuple[int, int],
        goal: tuple[int, int],
        banned_leakage: int = 0,
    ) -> tuple[Direction, Build | None] | None:
        start = self._find_start_tile(source[0], source[1], goal[0], goal[1])
        if start is None:
            return None
        gi = self.belief.idx(goal[0], goal[1])
        return self._build_chain(
            ct, pos, start, goal, goal_set={gi}, banned_leakage=banned_leakage
        )

    def _find_start_tile(
        self,
        sx: int,
        sy: int,
        gx: int,
        gy: int,
    ) -> tuple[int, int] | None:
        si = self.belief.idx(sx, sy)
        ent = self.belief.entity[si]
        if ent is None:
            return (sx, sy)
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
                d = (nx - gx) ** 2 + (ny - gy) ** 2
                if d < best_d:
                    best_d = d
                    best_start = (nx, ny)
            return best_start
        if etype in _TRANSPORT:
            d = self.belief.direction[si]
            bt = self.belief.bridge_target[si]
            if d is not None:
                dx, dy = d.delta()
                ox, oy = sx + dx, sy + dy
                if self.belief.in_bounds(ox, oy):
                    return (ox, oy)
            elif bt is not None:
                return bt
        return (sx, sy)

    def _build_chain_to_core(
        self,
        ct: Controller,
        pos: Position,
        source: tuple[int, int],
        banned_leakage: int = 0,
    ) -> tuple[Direction, Build | None] | None:
        cx, cy = self.belief.my_core
        start = self._find_start_tile(source[0], source[1], cx, cy)
        if start is None:
            return None
        return self._build_chain(
            ct, pos, start, (cx, cy), banned_leakage=banned_leakage
        )

    def _build_chain(
        self,
        ct: Controller,
        pos: Position,
        start: tuple[int, int],
        goal: tuple[int, int],
        goal_set: set[int] | None = None,
        banned_leakage: int = 0,
    ) -> tuple[Direction, Build | None] | None:
        sx, sy = start
        gx, gy = goal

        path = self._cached_chain_path
        if path is None or self._cached_chain_source != start:
            if self._flow_search is None or self._cached_chain_source != start:
                self._flow_search = flow_astar(
                    self.belief,
                    sx,
                    sy,
                    gx,
                    gy,
                    goal_set=goal_set,
                    banned_leakage=banned_leakage,
                )
                self._cached_chain_source = start
            self._flow_search.compute(ct, 1200)
            path = self._flow_search.get_path()
            if self._flow_search.done:
                self._flow_search = None
            self._cached_chain_path = path
        if path is None or len(path) < 2:
            self._cached_chain_path = None
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
