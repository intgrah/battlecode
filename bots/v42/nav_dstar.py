from algorithms.dstar import DStarLite
from map_belief import COST_EMPTY, COST_IMPASSABLE, MapBelief

WALK_8 = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]


class NavDStar:
    def __init__(self, belief: MapBelief) -> None:
        self.belief = belief
        w, h = belief.w, belief.h

        def successors(x: int, y: int) -> list[tuple[int, int, int]]:
            result: list[tuple[int, int, int]] = []
            for dx, dy in WALK_8:
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    wt = belief.walkable(nx, ny)
                    if wt < COST_IMPASSABLE:
                        result.append((nx, ny, wt))
            return result

        def heuristic(ax: int, ay: int, bx: int, by: int) -> int:
            dx = abs(ax - bx)
            dy = abs(ay - by)
            return max(dx, dy) * COST_EMPTY

        self._dstar = DStarLite(w, h, successors, successors, heuristic)
        self._goal: tuple[int, int] | None = None

    def set_goal(self, sx: int, sy: int, gx: int, gy: int) -> None:
        goal = (gx, gy)
        if goal != self._goal:
            self._dstar.initialize((sx, sy), goal)
            self._goal = goal
        else:
            self._dstar.set_start((sx, sy))

    def on_tile_changed(self, x: int, y: int) -> None:
        self._dstar.on_edge_change(x, y)

    def compute(self, budget: int = 200) -> None:
        self._dstar.compute(budget)

    def get_next_step(self) -> tuple[int, int] | None:
        return self._dstar.get_next_step()
