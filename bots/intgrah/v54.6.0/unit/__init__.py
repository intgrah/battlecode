from __future__ import annotations

from random import Random
from typing import TYPE_CHECKING

from util import DIR4, DIR8, W

from unit.blueprint import (
    core_for,
    find_core,
    identify_map,
    load_mirrored_blueprint,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from blueprint import BlueprintEntry
    from cambc import Controller, Direction, Position, Team
    from hardcode.known import KnownMap

__all__ = ["Unit"]


class Unit:
    def __init__(self) -> None:
        """ct-independent allocation. Runs in Player.__init__ (5s window)."""

    w: int
    """Actual map width."""
    h: int
    """Actual map height."""
    my_id: int
    """This unit's entity id."""
    my_team: Team
    """Allied team."""
    my_core: Position
    """Position of this team's core centre."""
    known_map: KnownMap | None
    """Identified known-map (None if unknown/identification failed)."""
    rng: Random
    """Random source, seeded with this unit's entity id."""
    blueprint: tuple[BlueprintEntry, ...]
    """Per-map blueprint, mirrored to this unit's team."""
    blueprint_positions: frozenset[Position]
    """Positions occupied by the (mirrored) blueprint on this team's side."""

    def post_init(self, ct: Controller) -> None:
        """ct-dependent init. Runs once on first turn for this unit."""
        self.w = ct.get_map_width()
        self.h = ct.get_map_height()
        self.my_id = ct.get_id()
        self.my_team = ct.get_team()
        self.rng = Random(self.my_id)
        core = find_core(ct, self.my_team)
        self.known_map = identify_map(ct, self.w, self.h, self.my_team, core)
        self.my_core = core if core is not None else (
            core_for(self.known_map, self.my_team) if self.known_map else Position(0, 0)
        )
        self.blueprint, self.blueprint_positions = load_mirrored_blueprint(
            self.known_map, self.w, self.h, self.my_team,
        )

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
        """Position to flat index. Stride is W=50 regardless of actual map size."""
        return pos.y * W + pos.x

    def in_bounds(self, pos: Position) -> bool:
        """Is in bounds of the actual map."""
        return 0 <= pos.x < self.w and 0 <= pos.y < self.h
