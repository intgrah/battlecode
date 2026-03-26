"""Navigate to unharvested Ax ore and place a harvester.

Only activates when Ti flow exists in the network, ensuring a future
foundry will have Ti input to pair with the Ax.

Same placement logic as harvest_ti: place immediately if adjacent, or
navigate to nearest and place on arrival.
"""

from cambc import Controller, Direction, Position
from marker import TaskClaim, TaskKind

from .base import BuilderBase
from .build import Action, PlaceHarvester


class HarvestAxMixin(BuilderBase):
    def _harvest_ax(
        self,
        ct: Controller,
        pos: Position,
    ) -> tuple[Direction, Action | None] | None:
        has_ti_flow = any(self.state.my_flow.ti[i] > 0 for i in self.state.my_transport)
        if not has_ti_flow:
            return None

        unharvested = (
            self.state.ore_ax - self.state.my_harvested - self.state.en_harvested
        )
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
                    return Direction.CENTRE, PlaceHarvester(ore_pos)

        w = self.state.w
        rnd = ct.get_current_round()
        candidates = sorted(
            unharvested,
            key=lambda o: (pos.x - o[0]) ** 2 + (pos.y - o[1]) ** 2,
        )
        for ore in candidates:
            oi = ore[1] * w + ore[0]
            ent = self.state.entity[oi]
            if ent is not None and ent[1] != self.state.my_team:
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
                        build = PlaceHarvester(ore_pos)
            self._claim = TaskClaim(TaskKind.NAV_ORE, oi, rnd)
            self._debug_target = (Position(ore[0], ore[1]), 255, 165, 0)
            return move, build
        return None
