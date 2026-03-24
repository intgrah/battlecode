from algorithms import Astar
from cambc import Controller
from map_belief import COST_EMPTY, COST_IMPASSABLE, MapBelief

WALK_8 = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]


class NavAstar(Astar[int]):
    def __init__(
        self,
        belief: MapBelief,
        sx: int,
        sy: int,
        gx: int,
        gy: int,
    ) -> None:
        self._belief = belief
        self._w = belief.w
        self._h = belief.h
        self._gx = gx
        self._gy = gy
        self._ct: Controller | None = None
        self._budget_us = 0
        si = sy * belief.w + sx
        gi = gy * belief.w + gx
        super().__init__(si, {gi})

    def set_budget(self, ct: Controller, budget_us: int) -> None:
        self._ct = ct
        self._budget_us = budget_us

    def should_continue(self) -> bool:
        if self._ct is None:
            return True
        return self._ct.get_cpu_time_elapsed() < self._budget_us

    def heuristic(self, node: int) -> int:
        dx = abs(node % self._w - self._gx)
        dy = abs(node // self._w - self._gy)
        return max(dx, dy) * COST_EMPTY

    def get_neighbors(self, node: int) -> list[tuple[int, int]]:
        w, h = self._w, self._h
        cx, cy = node % w, node // w
        result: list[tuple[int, int]] = []
        for dx, dy in WALK_8:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                wt = self._belief.walkable(nx, ny)
                if wt < COST_IMPASSABLE:
                    result.append((ny * w + nx, wt))
        return result
