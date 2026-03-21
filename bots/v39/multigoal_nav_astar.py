from astar import Astar
from map_belief import COST_IMPASSABLE, MapBelief

WALK_8 = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]


class MultiGoalNavAstar(Astar):
    def __init__(
        self,
        belief: MapBelief,
        sx: int,
        sy: int,
        goals: set[int],
    ) -> None:
        self.belief = belief
        self.goals = goals
        super().__init__(belief.w, belief.h, sx, sy)

    def is_goal(self, x: int, y: int) -> bool:
        return y * self.belief.w + x in self.goals

    def get_neighbors(self, cx: int, cy: int) -> list[tuple[int, int, int]]:
        b = self.belief
        w, h = b.w, b.h
        result: list[tuple[int, int, int]] = []
        for dx, dy in WALK_8:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                wt = b.walkable(nx, ny)
                if wt < COST_IMPASSABLE:
                    result.append((nx, ny, wt))
        return result

    def heuristic(self, x: int, y: int) -> int:
        return 0
