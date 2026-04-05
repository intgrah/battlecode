"""Exploration targets on a coarse grid.

Grid cells are spaced 9 tiles apart. A cell is marked visited when the
bot is close enough that the cell falls within vision (r²=20).
"""

from __future__ import annotations

from cambc import Position, Controller
from utils import chebyshev
import random

class ExploreGrid:
    def __init__(self, w: int, h: int) -> None:
        self._unvisited: set[Position] = set()
        self._next_target: Position | None = None
        self._changed: bool = False

        _SPACING = 9

        # Build 1D coordinate lists with both borders covered
        def _axis_coords(size: int) -> list[int]:
            n = max(1, (size - 1) // _SPACING)
            step = (size - 1) / n
            jitter = random.random() * step * 0.5

            coords: list[int] = [0]
            for i in range(1, n):
                coords.append(round(i * step + jitter))

            # Handle far border: snap last point if close, else add new one
            last = coords[-1] if coords else 0
            gap = (size - 1) - last
            if gap <= _SPACING * 3 // 4:
                coords[-1] = size - 1
            else:
                coords.append(size - 1)

            return coords

        xs = _axis_coords(w)
        ys = _axis_coords(h)
        for y in ys:
            for x in xs:
                self._unvisited.add(Position(x, y))

    def take_changed(self) -> bool:
        """Return whether the target changed, and reset the flag."""
        changed = self._changed
        self._changed = False
        return changed

    @property
    def target(self) -> Position | None:
        return self._next_target

    def update(self, ct: Controller, pos: Position, core: Position) -> None:
        """Remove visited cells and recompute target if needed."""
        self._unvisited -= {pos for pos in self._unvisited if ct.is_in_vision(pos)}

        if not self._unvisited:
            return

        cur = self._next_target
        if cur is not None and cur in self._unvisited:
            return

        best_dist = 1_000_000
        best: Position | None = None
        for cell in self._unvisited:
            d = chebyshev(core, cell) * 2 + chebyshev(pos, cell)
            if d < best_dist:
                best_dist = d
                best = cell

        self._next_target = best
        self._changed = True
    
    def draw_unvisited(self, ct: Controller, r: int, g: int, b: int) -> None:
        for cell in self._unvisited:
            ct.draw_indicator_dot(cell, r, g, b)
