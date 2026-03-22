from cambc import Controller, Direction, EntityType, Position
from entity import Entity
from map_belief import COST_IMPASSABLE, MapBelief
from marker import TaskClaim, TaskKind
from nav_dstar import NavDStar

from .build import Build, BuildKind


class BuilderBase(Entity):
    belief: MapBelief
    _last_claim: TaskClaim | None
    _claim: TaskClaim | None
    _debug_target: tuple[Position, int, int, int] | None
    _nav: NavDStar
    _nav_goal: tuple[int, int] | None

    def _move_toward(
        self,
        ct: Controller,
        pos: Position,
        target: Position,
    ) -> Direction:
        if pos == target:
            return Direction.CENTRE
        step = self._nav_step(pos, target)
        if step is None:
            return Direction.CENTRE
        nx, ny = step
        nxt = Position(nx, ny)
        bid = ct.get_tile_building_id(nxt)
        if bid is not None and ct.get_entity_type(bid) == EntityType.MARKER:
            ct.destroy(nxt)
        d = pos.direction_to(nxt)
        if ct.can_move(d):
            return d
        return Direction.CENTRE

    def _move_toward_with_road(
        self,
        ct: Controller,
        pos: Position,
        target: Position,
    ) -> tuple[Direction, Build | None]:
        if pos == target:
            return Direction.CENTRE, None
        step = self._nav_step(pos, target)
        if step is None:
            return Direction.CENTRE, None
        nx, ny = step
        nxt = Position(nx, ny)
        bid = ct.get_tile_building_id(nxt)
        if bid is not None and ct.get_entity_type(bid) == EntityType.MARKER:
            ct.destroy(nxt)
        d = pos.direction_to(nxt)
        if ct.can_move(d):
            return d, None
        road_cost, _ = ct.get_road_cost()
        ti, _ = ct.get_global_resources()
        if ti >= road_cost and ct.can_build_road(nxt):
            return d, Build(BuildKind.ROAD, nxt)
        return Direction.CENTRE, None

    def _nav_step(self, pos: Position, target: Position) -> tuple[int, int] | None:
        goal = (target.x, target.y)
        self._nav.set_goal(pos.x, pos.y, goal[0], goal[1])
        self._nav.compute(200)
        return self._nav.get_next_step()

    def _cardinal_adjacent(self, pos: Position, target: Position) -> Position | None:
        best = None
        best_dist = 999999
        for ddx, ddy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            ax, ay = target.x + ddx, target.y + ddy
            if not self.belief.in_bounds(ax, ay):
                continue
            if self.belief.walkable(ax, ay) >= COST_IMPASSABLE:
                continue
            dist = (pos.x - ax) ** 2 + (pos.y - ay) ** 2
            if dist < best_dist:
                best_dist = dist
                best = Position(ax, ay)
        return best

    def _is_claimed(self, tile_index: int, kind: TaskKind) -> bool:
        for c in self.belief.claims:
            if c.tile_index == tile_index and c.kind == kind:
                if (
                    self._last_claim is not None
                    and c.tile_index == self._last_claim.tile_index
                    and c.kind == self._last_claim.kind
                ):
                    continue
                return True
        return False
