"""Exploration targets on a coarse grid.

Grid cells are spaced 9 tiles apart. A cell is marked visited when the
bot is close enough that the cell falls within vision (r²=20).
"""

from __future__ import annotations

from cambc import Position, Controller
from utils import chebyshev


class ExploreGrid:
    def __init__(self, w: int, h: int) -> None:
        self._unvisited: set[Position] = set()
        self._next_target: Position | None = None

        _SPACING = 13

        # Build grid cells offset so the first cell is at (SPACING//2, SPACING//2)
        for y in range(0, h + _SPACING // 2, _SPACING):
            for x in range(0, w + _SPACING // 2, _SPACING):
                pos = Position(min(x, w - 1), min(y, h - 1))
                self._unvisited.add(pos)

    def update(self, ct: Controller) -> None:
        """Remove any grid cell within vision of the bot's position."""
        self._unvisited -= { pos for pos in self._unvisited if ct.is_in_vision(pos) }

    def select_next_target(self, pos: Position, core: Position) -> Position | None:
        """Return the unvisited cell nearest to the friendly core."""
        if not self._unvisited:
            return None
        
        next = self._next_target
        if next is not None and next in self._unvisited:
            return next
        
        best_dist = 1_000_000
        for cell in self._unvisited:
            # prefer nearer to core than nearer to bbot
            d = chebyshev(core, cell) * 2 + chebyshev(pos, cell)
            if d < best_dist:
                best_dist = d
                next = cell

        self._next_target = next
        return next
    
    def draw_unvisited(self, ct: Controller) -> None:
        for cell in self._unvisited:
            ct.draw_indicator_dot(cell, 255, 0, 0)
