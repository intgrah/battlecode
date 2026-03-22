from typing import TYPE_CHECKING

from astar import Astar
from map_belief import COST_EMPTY, COST_IMPASSABLE, MapBelief

if TYPE_CHECKING:
    from cambc import Controller

WALK_8 = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]


class NavAstar(Astar):
    def __init__(
        self,
        belief: MapBelief,
        sx: int,
        sy: int,
        gx: int,
        gy: int,
    ) -> None:
        self.belief = belief
        self.gx = gx
        self.gy = gy
        self.min_cost = COST_EMPTY
        super().__init__(belief.w, belief.h, sx, sy)

    def is_goal(self, x: int, y: int) -> bool:
        return x == self.gx and y == self.gy

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
        dx = abs(x - self.gx)
        dy = abs(y - self.gy)
        return max(dx, dy) * self.min_cost


def nav_astar(
    belief: MapBelief,
    sx: int,
    sy: int,
    gx: int,
    gy: int,
    ct: "Controller",
    budget_us: int = 1800,
) -> list[tuple[int, int]] | None:
    search = NavAstar(belief, sx, sy, gx, gy)
    search.compute(ct, budget_us)
    return search.get_path()
