from cambc import Controller, Direction, Position
from entity import Entity
from map_belief import COST_IMPASSABLE, MapBelief
from marker import TaskClaim, TaskKind
from nav_astar import NavAstar

from .build import Action, PlaceRoad


class BuilderBase(Entity):
    belief: MapBelief
    _last_claim: TaskClaim | None
    _claim: TaskClaim | None
    _debug_target: tuple[Position, int, int, int] | None
    _nav_target_key: tuple[int, int] | None
    _nav_path: list[int] | None
    _nav_search: NavAstar | None

    def _move_toward(
        self,
        ct: Controller,
        pos: Position,
        target: Position,
    ) -> Direction:
        if pos == target:
            return Direction.CENTRE
        search = NavAstar(self.belief, pos.x, pos.y, target.x, target.y)
        search.set_budget(ct, 5000)
        search.compute()
        raw = search.get_path()
        if raw is None or len(raw) < 2:
            return Direction.CENTRE
        w = self.belief.w
        nx, ny = raw[1] % w, raw[1] // w
        nxt = Position(nx, ny)
        d = pos.direction_to(nxt)
        if ct.can_move(d):
            return d
        return Direction.CENTRE

    def _move_toward_with_road(
        self,
        ct: Controller,
        pos: Position,
        target: Position,
    ) -> tuple[Direction, Action | None]:
        if pos == target:
            return Direction.CENTRE, None

        target_key = (target.x, target.y)
        if self._nav_target_key != target_key:
            self._nav_target_key = target_key
            self._nav_path = None
            self._nav_search = None

        # If we have a cached path, follow it
        if self._nav_path is not None:
            w = self.belief.w
            pi = pos.y * w + pos.x
            if pi in self._nav_path:
                idx = self._nav_path.index(pi)
                if idx + 1 < len(self._nav_path):
                    nxt_i = self._nav_path[idx + 1]
                    nx, ny = nxt_i % w, nxt_i // w
                    nxt = Position(nx, ny)
                    d = pos.direction_to(nxt)
                    if ct.can_move(d):
                        return d, None
                    road_cost, _ = ct.get_road_cost()
                    ti, _ = ct.get_global_resources()
                    if ti >= road_cost and ct.can_build_road(nxt):
                        return d, PlaceRoad(nxt)
            # Path invalid (not on it), recompute
            self._nav_path = None
            self._nav_search = None

        # Compute or resume A*
        if self._nav_search is None:
            self._nav_search = NavAstar(self.belief, pos.x, pos.y, target.x, target.y)
        self._nav_search.set_budget(ct, 1800)
        self._nav_search.compute()
        if not self._nav_search.done:
            return Direction.CENTRE, None
        raw = self._nav_search.get_path()
        if raw is None or len(raw) < 2:
            return Direction.CENTRE, None
        self._nav_path = raw
        self._nav_search = None
        w = self.belief.w
        nx, ny = raw[1] % w, raw[1] // w
        nxt = Position(nx, ny)
        d = pos.direction_to(nxt)
        if ct.can_move(d):
            return d, None
        road_cost, _ = ct.get_road_cost()
        ti, _ = ct.get_global_resources()
        if ti >= road_cost and ct.can_build_road(nxt):
            return d, PlaceRoad(nxt)
        return Direction.CENTRE, None

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
