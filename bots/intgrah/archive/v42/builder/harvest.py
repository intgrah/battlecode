from cambc import Controller, Direction, Position
from marker import TaskClaim, TaskKind

from .base import BuilderBase
from .build import Build, BuildKind


class HarvestMixin(BuilderBase):
    def _harvest_ti(
        self,
        ct: Controller,
        pos: Position,
    ) -> tuple[Direction, Build | None] | None:
        return self._harvest_impl(
            ct,
            pos,
            self.belief.ore_ti - self.belief.my_harvested - self.belief.en_harvested,
        )

    def _harvest_ax(
        self,
        ct: Controller,
        pos: Position,
    ) -> tuple[Direction, Build | None] | None:
        has_ti_flow = any(
            self.belief.my_flow.ti[i] > 0 for i in self.belief.my_transport
        )
        if not has_ti_flow:
            return None
        return self._harvest_impl(
            ct,
            pos,
            self.belief.ore_ax - self.belief.my_harvested - self.belief.en_harvested,
        )

    def _harvest_impl(
        self,
        ct: Controller,
        pos: Position,
        unharvested: set[tuple[int, int]],
    ) -> tuple[Direction, Build | None] | None:
        if not unharvested:
            return None

        for ddx, ddy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            p = (pos.x + ddx, pos.y + ddy)
            if p in unharvested:
                ore_pos = Position(p[0], p[1])
                bid = ct.get_tile_building_id(ore_pos)
                if bid is not None:
                    if ct.can_destroy(ore_pos):
                        ct.destroy(ore_pos)
                    else:
                        continue
                h_cost, _ = ct.get_harvester_cost()
                ti, _ = ct.get_global_resources()
                if ti >= h_cost and ct.can_build_harvester(ore_pos):
                    return Direction.CENTRE, Build(BuildKind.HARVESTER, ore_pos)

        w = self.belief.w
        rnd = ct.get_current_round()
        candidates = sorted(
            unharvested,
            key=lambda o: (pos.x - o[0]) ** 2 + (pos.y - o[1]) ** 2,
        )
        for ore in candidates:
            oi = ore[1] * w + ore[0]
            ent = self.belief.entity[oi]
            if ent is not None and ent[1] != self.belief.my_team:
                continue
            if self._is_claimed(oi, TaskKind.NAV_ORE):
                continue
            adj = self._cardinal_adjacent(pos, Position(ore[0], ore[1]))
            if adj is None:
                continue
            move, build = self._move_toward_with_road(ct, pos, adj)
            if move != Direction.CENTRE and build is None:
                new_pos = pos.add(move)
                ore_pos = Position(ore[0], ore[1])
                if new_pos.distance_squared(ore_pos) == 1:
                    bid = ct.get_tile_building_id(ore_pos)
                    if bid is not None and ct.can_destroy(ore_pos):
                        ct.destroy(ore_pos)
                    h_cost, _ = ct.get_harvester_cost()
                    ti, _ = ct.get_global_resources()
                    if ti >= h_cost:
                        build = Build(BuildKind.HARVESTER, ore_pos)
            self._claim = TaskClaim(TaskKind.NAV_ORE, oi, rnd)
            self._debug_target = (Position(ore[0], ore[1]), 0, 255, 0)
            return move, build
        return None
