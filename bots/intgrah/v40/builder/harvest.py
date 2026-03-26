from cambc import Controller, Direction, Position
from marker import TaskClaim, TaskKind

from .base import BuilderBase
from .build import Build, BuildKind


class HarvestMixin(BuilderBase):
    def _place_harvester(
        self,
        ct: Controller,
        pos: Position,
    ) -> tuple[Direction, Build | None]:
        unharvested = (
            (self.belief.ore_ti | self.belief.ore_ax)
            - self.belief.my_harvested
            - self.belief.en_harvested
        )
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
        return Direction.CENTRE, None

    def _nav_ore(
        self,
        ct: Controller,
        pos: Position,
    ) -> tuple[Direction, Build | None] | None:
        unharvested = (
            self.belief.ore_ti - self.belief.my_harvested - self.belief.en_harvested
        )
        if not unharvested:
            return None
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
            if adj is not None:
                move, build = self._move_toward_with_road(ct, pos, adj)
                self._claim = TaskClaim(TaskKind.NAV_ORE, oi, rnd)
                self._debug_target = (Position(ore[0], ore[1]), 0, 255, 0)
                return move, build
        return None
