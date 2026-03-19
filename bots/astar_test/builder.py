from astar import EDGES_ROAD, astar
from cambc import Controller, EntityType, Position
from entity import Entity
from map_belief import MapBelief


class ExploreBuilder(Entity):
    def __init__(self, ct: Controller) -> None:
        super().__init__(ct)
        self.core_pos = self._find_core(ct)
        self.belief = MapBelief(
            self.w, self.h, self.team, (self.core_pos.x, self.core_pos.y),
        )
        self.target: Position | None = None
        self.explore_radius = 0
        self.done = False
        self.prev_pos: tuple[int, int] | None = None

    def run(self, ct: Controller) -> None:
        if self.done:
            return

        self.belief.update(ct)
        pos = ct.get_position()

        self._advance_frontier()

        unseen = sum(1 for e in self.belief.env if e is None)
        if unseen == 0:
            self.done = True
            return

        if self.target is None or pos == self.target:
            self.target = self._pick_frontier_target(pos)

        if self.target is None:
            return

        path = astar(
            self.belief,
            pos.x,
            pos.y,
            self.target.x,
            self.target.y,
            EDGES_ROAD,
            ct=ct,
        )
        if path is None or len(path) < 2:
            self.target = None
            return

        nx, ny = path[1]
        d = pos.direction_to(Position(nx, ny))

        if ct.can_move(d):
            ct.move(d)
        else:
            nxt = Position(nx, ny)
            road_cost, _ = ct.get_road_cost()
            ti, _ = ct.get_global_resources()
            if ti >= road_cost and ct.can_build_road(nxt):
                ct.build_road(nxt)
                if ct.can_move(d):
                    ct.move(d)

    def _find_core(self, ct: Controller) -> Position:
        my = ct.get_team()
        for bid in ct.get_nearby_buildings():
            if ct.get_team(bid) == my and ct.get_entity_type(bid) == EntityType.CORE:
                return ct.get_position(bid)
        raise AssertionError

    def _advance_frontier(self) -> None:
        cx, cy = self.core_pos.x, self.core_pos.y
        limit = max(self.w, self.h)
        while self.explore_radius < limit:
            r = self.explore_radius + 1
            if self._ring_has_unseen(cx, cy, r):
                break
            self.explore_radius = r

    def _ring_has_unseen(self, cx: int, cy: int, r: int) -> bool:
        x0, x1 = max(0, cx - r), min(self.w - 1, cx + r)
        y0, y1 = max(0, cy - r), min(self.h - 1, cy + r)
        for x in range(x0, x1 + 1):
            if self.belief.in_bounds(x, y0) and self.belief.is_unseen(x, y0):
                return True
            if self.belief.in_bounds(x, y1) and self.belief.is_unseen(x, y1):
                return True
        for y in range(y0 + 1, y1):
            if self.belief.in_bounds(x0, y) and self.belief.is_unseen(x0, y):
                return True
            if self.belief.in_bounds(x1, y) and self.belief.is_unseen(x1, y):
                return True
        return False

    def _pick_frontier_target(self, pos: Position) -> Position | None:
        cx, cy = self.core_pos.x, self.core_pos.y
        r = self.explore_radius + 1
        x0, x1 = max(0, cx - r), min(self.w - 1, cx + r)
        y0, y1 = max(0, cy - r), min(self.h - 1, cy + r)
        candidates: list[tuple[int, int]] = []
        for x in range(x0, x1 + 1):
            if self.belief.in_bounds(x, y0) and self.belief.is_unseen(x, y0):
                candidates.append((x, y0))
            if self.belief.in_bounds(x, y1) and self.belief.is_unseen(x, y1):
                candidates.append((x, y1))
        for y in range(y0 + 1, y1):
            if self.belief.in_bounds(x0, y) and self.belief.is_unseen(x0, y):
                candidates.append((x0, y))
            if self.belief.in_bounds(x1, y) and self.belief.is_unseen(x1, y):
                candidates.append((x1, y))
        if candidates:
            cx, cy = self.core_pos.x, self.core_pos.y
            candidates.sort(
                key=lambda c: (
                    (c[0] - pos.x) ** 2
                    + (c[1] - pos.y) ** 2
                    - ((c[0] - cx) ** 2 + (c[1] - cy) ** 2) // 4
                ),
            )
            return Position(candidates[0][0], candidates[0][1])
        return None
