"""Translation of `bots/intgrah/v54.7.9/util/symmetry.py`."""

from __future__ import annotations

from enum import IntEnum
from typing import Final

from cambc import Position


class Symmetry(IntEnum):
    """All maps exhibit one of these symmetries."""

    Rot = 0
    Hor = 1
    Ver = 2

    def action(self, pos, w, h):
        """Apply this symmetry to `pos` on a map with the given dimensions."""
        match self:
            case Symmetry.Rot:
                return Position(x=w - 1 - pos.x, y=h - 1 - pos.y)
            case Symmetry.Hor:
                return Position(x=pos.x, y=h - 1 - pos.y)
            case Symmetry.Ver:
                return Position(x=w - 1 - pos.x, y=pos.y)


ALL: Final[list[Symmetry]] = [Symmetry.Rot, Symmetry.Hor, Symmetry.Ver]
"""
All three symmetries, in priority order (matches Python's
`Symmetry` enum iteration order).
"""
