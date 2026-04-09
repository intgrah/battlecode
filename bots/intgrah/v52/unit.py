from __future__ import annotations

from abc import ABC, abstractmethod
from random import Random
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from cambc import Controller, Position, Team

__all__ = ["Unit"]


class Unit(ABC):
    def __init__(self, ct: Controller) -> None:
        self.w: Final[int] = ct.get_map_width()
        self.h: Final[int] = ct.get_map_height()
        self.my_team: Final[Team] = ct.get_team()
        self.rng: Final[Random] = Random(ct.get_id())

    @abstractmethod
    def run(self, ct: Controller) -> None: ...

    def idx(self, pos: Position) -> int:
        """Position to flat index"""
        return pos.y * self.w + pos.x

    def in_bounds(self, pos: Position) -> bool:
        """Is in bounds of map"""
        return 0 <= pos.x < self.w and 0 <= pos.y < self.h
