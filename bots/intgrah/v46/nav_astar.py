from __future__ import annotations

from typing import TYPE_CHECKING

from algorithms import Astar
from builder.state import COST_IMPASSABLE, COST_ROAD, State
from util import DIR8_DELTA

if TYPE_CHECKING:
    from hardcode.apsp_loader import ApspTable


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
        self._apsp: ApspTable | None = state.apsp
        self._gi = gy * state.w + gx
        si = sy * state.w + sx
        super().__init__(si, {self._gi})

    def heuristic(self, node: int) -> int:
        apsp = self._apsp
        if apsp is not None:
            d = apsp.dist(node, self._gi)
            return d * COST_ROAD if d < 255 else 1_000_000
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
