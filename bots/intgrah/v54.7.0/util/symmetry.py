from enum import StrEnum

from cambc import Position

__all__ = ["Symmetry"]


class Symmetry(StrEnum):
    """All maps exhibit one of these symmetries."""

    ROT = "rot"
    """180° rotation about the map centre. Point reflection."""
    HOR = "hor"
    """Reflection across the horizontal axis. x unchanged, y flipped."""
    VER = "ver"
    """Reflection across the vertical axis. x flipped, y unchanged."""

    def action(self, pos: Position, w: int, h: int) -> Position:
        """The action of this symmetry to `pos` on a map with known dimensions."""
        match self:
            case Symmetry.ROT:
                return Position(w - 1 - pos.x, h - 1 - pos.y)
            case Symmetry.HOR:
                return Position(pos.x, h - 1 - pos.y)
            case Symmetry.VER:
                return Position(w - 1 - pos.x, pos.y)
