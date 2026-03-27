from algorithms import Astar
from builder.state import COST_IMPASSABLE, COST_ROAD, State
from util import DIR8_DELTA


class NavAstar(Astar[int]):
    def __init__(
        self,
        state: State,
        sx: int,
        sy: int,
        gx: int,
        gy: int,
    ) -> None:
        self._state = state
        self._w = state.w
        self._h = state.h
        self._gx = gx
        self._gy = gy
        si = sy * state.w + sx
        gi = gy * state.w + gx
        super().__init__(si, {gi})

    def heuristic(self, node: int) -> int:
        y, x = divmod(node, self._w)
        dx = abs(x - self._gx)
        dy = abs(y - self._gy)
        return max(dx, dy) * COST_ROAD

    def get_neighbors(self, node: int) -> list[tuple[int, int]]:
        w, h = self._w, self._h
        cx, cy = node % w, node // w
        result: list[tuple[int, int]] = []
        for dx, dy in DIR8_DELTA:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                wt = self._state.walkable(nx, ny)
                if wt < COST_IMPASSABLE:
                    if dx != 0 and dy != 0:
                        wt += 1
                    result.append((ny * w + nx, wt))
        return result
