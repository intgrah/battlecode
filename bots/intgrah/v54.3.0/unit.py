from __future__ import annotations

from abc import ABC
from random import Random
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from cambc import Controller, Position, Team

__all__ = ["Unit"]


class Unit(ABC):
    my_pos: Position
    """This unit's position, updated at the start of the turn."""

    def __init__(self, ct: Controller) -> None:
        self.w: Final[int] = ct.get_map_width()
        """Map width."""
        self.h: Final[int] = ct.get_map_height()
        """Map height."""
        self.my_id: Final[int] = ct.get_id()
        """This unit's entity id."""
        self.my_team: Final[Team] = ct.get_team()
        """Allied team."""
        self.rng: Final[Random] = Random(self.my_id)
        """Random source, seeded with this unit's entity id."""

    def run(self, ct: Controller) -> None:
        self.my_pos = ct.get_position()

    def idx(self, pos: Position) -> int:
        """Position to flat index."""
        return pos.y * self.w + pos.x

    def in_bounds(self, pos: Position) -> bool:
        """Is in bounds of map."""
        return 0 <= pos.x < self.w and 0 <= pos.y < self.h
