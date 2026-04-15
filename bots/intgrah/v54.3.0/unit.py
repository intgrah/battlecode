from __future__ import annotations

from abc import ABC
from random import Random
from typing import TYPE_CHECKING, Final

from util import DIR4, DIR8

if TYPE_CHECKING:
    from collections.abc import Iterable

    from cambc import Controller, Direction, Position, Team

__all__ = ["Unit"]


class Unit(ABC):
    def __init__(self, ct: Controller) -> None:
        """Initialise immutable per-unit state (map dimensions, id, team, rng)."""
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
    round: int
    """Current round number."""
    ti: int
    """Global titanium at the start of the turn."""
    ax: int
    """Global (refined) axionite at the start of the turn."""
    scale: float
    """Scale percent / 100 at the start of the turn."""
    neighbours_4: Iterable[Position]
    """Cardinal neighbour positions of my_pos, in-bounds only."""
    neighbours_8: Iterable[Position]
    """All 8 neighbour positions of my_pos, in-bounds only."""
    dir_neighbours_4: Iterable[tuple[Direction, Position]]
    """Cardinal (direction, position) pairs from my_pos, in-bounds only."""
    dir_neighbours_8: Iterable[tuple[Direction, Position]]
    """All 8 (direction, position) pairs from my_pos, in-bounds only."""

    def run(self, ct: Controller) -> None:
        """Cache per-turn state: position, neighbours, visible bots, resources."""
        self.my_pos = ct.get_position()
        self.dir_neighbours_4 = tuple(
            (d, p) for d in DIR4 if self.in_bounds(p := self.my_pos.add(d))
        )
        self.dir_neighbours_8 = tuple(
            (d, p) for d in DIR8 if self.in_bounds(p := self.my_pos.add(d))
        )
        self.neighbours_4 = tuple(p for _, p in self.dir_neighbours_4)
        self.neighbours_8 = tuple(p for _, p in self.dir_neighbours_8)
        self.round = ct.get_current_round()
        self.ti, self.ax = ct.get_global_resources()
        self.scale = ct.get_scale_percent() / 100
        self.nearby_tiles = ct.get_nearby_tiles()
        self.enemy_bots: set[Position] = set()
        self.friendly_bots: set[Position] = set()
        self.all_bots: dict[Position, int] = {}
        for pos in self.nearby_tiles:
            uid = ct.get_tile_builder_bot_id(pos)
            if uid is not None:
                self.all_bots[pos] = uid
                if ct.get_team(uid) == self.my_team:
                    if uid != self.my_id:
                        self.friendly_bots.add(pos)
                else:
                    self.enemy_bots.add(pos)

    def idx(self, pos: Position) -> int:
        """Position to flat index."""
        return pos.y * self.w + pos.x

    def in_bounds(self, pos: Position) -> bool:
        """Is in bounds of map."""
        return 0 <= pos.x < self.w and 0 <= pos.y < self.h
