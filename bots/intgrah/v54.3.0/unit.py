from __future__ import annotations

from abc import ABC, abstractmethod
from random import Random
from typing import TYPE_CHECKING, Final, override

if TYPE_CHECKING:
    from cambc import Controller, Position, Team

__all__ = ["StationaryUnit", "Unit"]


class Unit(ABC):
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

    @abstractmethod
    def run(self, ct: Controller) -> None: ...

    def idx(self, pos: Position) -> int:
        """Position to flat index."""
        return pos.y * self.w + pos.x

    def in_bounds(self, pos: Position) -> bool:
        """Is in bounds of map."""
        return 0 <= pos.x < self.w and 0 <= pos.y < self.h


class StationaryUnit(Unit):
    @override
    def __init__(self, ct: Controller) -> None:
        super().__init__(ct)
        self.my_pos: Final[Position] = ct.get_position()
        """This unit's static position."""
