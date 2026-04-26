from enum import IntEnum
from typing import override

from cambc import Position

__all__ = ["Symmetry"]


class Symmetry(IntEnum):
    """All maps exhibit one of these symmetries."""

    ROT = 0
    """180° rotation about the map centre. Point reflection."""
    HOR = 1
    """Reflection across the horizontal axis. x unchanged, y flipped."""
    VER = 2
    """Reflection across the vertical axis. x flipped, y unchanged."""

    @override
    def __str__(self) -> str:
        return self.name

    @override
    def __repr__(self) -> str:
        return f"Symmetry.{self.name}"

    def action(self, pos: Position, w: int, h: int) -> Position:
        """The action of this symmetry to `pos` on a map with known dimensions."""
        match self:
            case Symmetry.ROT:
                return Position(w - 1 - pos.x, h - 1 - pos.y)
            case Symmetry.HOR:
                return Position(pos.x, h - 1 - pos.y)
            case Symmetry.VER:
                return Position(w - 1 - pos.x, pos.y)
