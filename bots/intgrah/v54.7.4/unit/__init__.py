from __future__ import annotations

from abc import abstractmethod
from random import Random
from typing import TYPE_CHECKING, override

from cambc import EntityType
from marker import find_symmetry_marker
from util.constants import MAX_WIDTH
from util.directions import DIR4, DIR8
from util.symmetry import Symmetry

if TYPE_CHECKING:
    from collections.abc import Iterable

    from cambc import Controller, Direction, Environment, Position, Team

__all__ = ["CoreAwareUnit", "Unit"]


class Unit:
    def __init__(self) -> None:
        """ct-independent allocation. Runs in Player.__init__ (5s window)."""
        self.symmetry_candidates: set[Symmetry] = set(Symmetry)

    w: int
    """Actual map width."""
    h: int
    """Actual map height."""
    my_id: int
    """This unit's entity id."""
    my_team: Team
    """Allied team."""
    rng: Random
    """Random source, seeded with this unit's entity id."""

    def post_init(self, ct: Controller) -> None:
        """ct-dependent init. Runs once on first turn for this unit."""
        self.w = ct.get_map_width()
        self.h = ct.get_map_height()
        self.my_id = ct.get_id()
        self.my_team = ct.get_team()
        self.rng = Random(self.my_id)
        self._narrow_symmetry_from_vision(ct)

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
        self._check_symmetry_marker(ct)

    def idx(self, pos: Position) -> int:
        """Position to flat index. Stride is W=50 regardless of actual map size."""
        return pos.y * MAX_WIDTH + pos.x

    def in_bounds(self, pos: Position) -> bool:
        """Is in bounds of the actual map."""
        return 0 <= pos.x < self.w and 0 <= pos.y < self.h

    @property
    def symmetry(self) -> Symmetry | None:
        """Resolved symmetry iff exactly one candidate remains."""
        if len(self.symmetry_candidates) == 1:
            return next(iter(self.symmetry_candidates))
        return None

    @property
    def symmetry_guess(self) -> Symmetry:
        """A Symmetry value usable for mirroring even when unresolved.
        Picks the first surviving candidate in preference order
        ROT → VER → HOR; falls back to ROT if all have been eliminated
        (shouldn't happen on a valid map).
        """
        for sym in (Symmetry.ROT, Symmetry.VER, Symmetry.HOR):
            if sym in self.symmetry_candidates:
                return sym
        return Symmetry.ROT

    def _narrow_symmetry_from_vision(self, ct: Controller) -> None:
        """One-shot narrowing using only what we can see right now. For
        static units (core, turrets) this is the only chance — they don't
        move, so their vision never grows.
        """
        if self.symmetry is not None:
            return
        vision: dict[Position, tuple[Environment, bool]] = {}
        for pos in ct.get_nearby_tiles():
            bid = ct.get_tile_building_id(pos)
            is_core = bid is not None and ct.get_entity_type(bid) == EntityType.CORE
            vision[pos] = (ct.get_tile_env(pos), is_core)
        invalid: set[Symmetry] = set()
        for sym in self.symmetry_candidates:
            for pos, val in vision.items():
                other = vision.get(sym.action(pos, self.w, self.h))
                if other is not None and other != val:
                    invalid.add(sym)
                    break
        self.symmetry_candidates -= invalid

    def _check_symmetry_marker(self, ct: Controller) -> None:
        if self.symmetry is not None:
            return
        sym = find_symmetry_marker(ct, self.nearby_tiles, self.my_team)
        if sym is not None:
            self.symmetry_candidates = {sym}


class CoreAwareUnit(Unit):
    """Unit that knows where its allied core is. Subclassed by Core
    (which IS the core) and Builder (spawned next to it). Turrets stay
    as plain `Unit` because they may be built far from the core.
    """

    my_core: Position

    @override
    def post_init(self, ct: Controller) -> None:
        super().post_init(ct)
        self.my_core = self._resolve_my_core(ct)

    @abstractmethod
    def _resolve_my_core(self, ct: Controller) -> Position:
        """Return the position of this unit's allied core. Called once
        at post_init to populate `self.my_core`. Core returns its own
        position; Builder scans vision via `find_core`.
        """
        ...

    @property
    def en_core_guess(self) -> Position:
        """Best guess at the enemy core position: mirrors `my_core`
        under `symmetry_guess`. Exact once symmetry is resolved.
        """
        return self.symmetry_guess.action(self.my_core, self.w, self.h)
