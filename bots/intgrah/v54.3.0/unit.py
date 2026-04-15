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
    nearby_tiles: list[Position]
    """Tiles within vision, updated at the start of the turn."""
    enemy_bots: set[Position]
    """Positions of visible enemy builder bots."""
    friendly_bots: set[Position]
    """Positions of visible friendly builder bots (excluding self)."""
    all_bots: dict[Position, int]
    """Position to entity id of all visible builder bots."""

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
        self.nearby_tiles = ct.get_nearby_tiles()
        self.enemy_bots = set()
        self.friendly_bots = set()
        self.all_bots = {}
        my_team = self.my_team
        my_id = self.my_id
        for pos in self.nearby_tiles:
            uid = ct.get_tile_builder_bot_id(pos)
            if uid is not None:
                self.all_bots[pos] = uid
                if ct.get_team(uid) != my_team:
                    self.enemy_bots.add(pos)
                elif uid != my_id:
                    self.friendly_bots.add(pos)

    def idx(self, pos: Position) -> int:
        """Position to flat index."""
        return pos.y * self.w + pos.x

    def in_bounds(self, pos: Position) -> bool:
        """Is in bounds of map."""
        return 0 <= pos.x < self.w and 0 <= pos.y < self.h
