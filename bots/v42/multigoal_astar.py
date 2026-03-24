from astar import Astar
from map_belief import COST_IMPASSABLE, MapBelief

WALK_8 = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]


def _build_edges(belief: MapBelief) -> list[list[tuple[int, int]]]:
    w, h = belief.w, belief.h
    n = w * h
    edges: list[list[tuple[int, int]]] = [[] for _ in range(n)]
    for i in range(n):
        cx, cy = i % w, i // w
        for dx, dy in WALK_8:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                wt = belief.walkable(nx, ny)
                if wt < COST_IMPASSABLE:
                    edges[i].append((ny * w + nx, wt))
    return edges


class MultiGoalNavAstar(Astar):
    def __init__(
        self,
        belief: MapBelief,
        sx: int,
        sy: int,
        goals: set[int],
    ) -> None:
        self.belief = belief
        n = belief.w * belief.h
        h_table = [0] * n
        edges = _build_edges(belief)
        super().__init__(belief.w, belief.h, sx, sy, goals, edges, h_table)

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
        return x - x + y - y
