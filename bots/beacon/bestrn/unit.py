"""
Translation of `bots/intgrah/v54.7.9/unit/__init__.py`.

Models the Python `Unit` / `CoreAwareUnit` class hierarchy as two traits
plus a shared `UnitState` struct. Concrete unit types (Breach, Gunner,
Builder, Core, …) embed a `UnitState` and implement `Unit::state` /
`state_mut`; `CoreAwareUnit` adds `my_core` access on top.

Per-turn caching mirrors Python:
- `post_init(ct)`: ct-dependent one-shot init. Populates `width`, `height`,
  `my_id`, `my_team`, `rng`, then narrows symmetry from initial vision.
- `run(ct)`: caches `my_pos`, neighbours, round, resources, visible bots,
  and checks for an allied symmetry marker in vision.
"""

from __future__ import annotations

from cambc import EntityType, Position, Team
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Controller, ControllerApi, Direction, Environment
from marker import find_symmetry_marker
from util.constants import MAX_WIDTH
from util.directions import DIR4, DIR8
from util.symmetry import ALL, Symmetry
from random import Random as Rng


class UnitState:
    """
    Per-turn cached state shared by every unit. Concrete units embed this and
    access via `Unit::state` / `state_mut`.
    """

    width: int
    height: int
    my_id: int
    my_team: Team
    rng: Rng
    my_pos: Position
    nearby_tiles: list[Position]
    enemy_bots: set[Position]
    friendly_bots: set[Position]
    all_bots: dict[Position, int]
    round: int
    ti: int
    ax: int
    scale: float
    dir_neighbours_4: list[tuple[Direction, Position]]
    dir_neighbours_8: list[tuple[Direction, Position]]
    neighbours_4: list[Position]
    neighbours_8: list[Position]
    symmetry_candidates: set[Symmetry]

    def __init__(self):
        """
        ct-independent allocation. Mirrors Python `Unit.__init__` — runs in
        `Player::default()` (5s window).
        """
        symmetry_candidates: set[Symmetry] = set()
        for s in ALL:
            symmetry_candidates.add(s)
        self.width = 0
        self.height = 0
        self.my_id = 0
        self.my_team = Team.A
        self.rng = Rng(0)
        self.my_pos = Position(x=0, y=0)
        self.nearby_tiles = []
        self.enemy_bots = set()
        self.friendly_bots = set()
        self.all_bots = {}
        self.round = 0
        self.ti = 0
        self.ax = 0
        self.scale = 0.0
        self.dir_neighbours_4 = []
        self.dir_neighbours_8 = []
        self.neighbours_4 = []
        self.neighbours_8 = []
        self.symmetry_candidates = symmetry_candidates

    @staticmethod
    def default():
        return UnitState()

    def init_static_state(self, ct):
        """
        One-time setup shared by every unit. Concrete `Unit::post_init`
        impls call this on their `state` field — the receiver is concrete
        `&mut UnitState`, so pyrust translates field accesses cleanly.
        """
        self.width = ct.get_map_width()
        self.height = ct.get_map_height()
        self.my_id = ct.get_id()
        self.my_team = ct.get_team(None)
        self.rng = Rng(int(self.my_id))

    def cache_per_turn_state(self, ct):
        """
        Per-turn caching shared by every unit: position, neighbours, round,
        resources, visible bots. Concrete `Unit::run` impls call this on
        their `state` field.
        """
        my_pos = ct.get_position(None)
        width = self.width
        height = self.height
        my_team = self.my_team
        my_id = self.my_id
        dir_neighbours_4: list[tuple[Direction, Position]] = []
        for d in DIR4:
            p = my_pos.add(d)
            if in_bounds(p, width, height):
                dir_neighbours_4.append((d, p))
        dir_neighbours_8: list[tuple[Direction, Position]] = []
        for d in DIR8:
            p = my_pos.add(d)
            if in_bounds(p, width, height):
                dir_neighbours_8.append((d, p))
        neighbours_4: list[Position] = list((t[1] for t in dir_neighbours_4))
        neighbours_8: list[Position] = list((t[1] for t in dir_neighbours_8))
        round = ct.get_current_round()
        ti, ax = ct.get_global_resources()
        scale = ct.get_scale_percent() / 100.0
        nearby_tiles = ct.get_nearby_tiles(None)
        enemy_bots: set[Position] = set()
        friendly_bots: set[Position] = set()
        all_bots: dict[Position, int] = {}
        for pos in nearby_tiles:
            uid = ct.get_tile_builder_bot_id(pos)
            if uid is None:
                continue
            all_bots[pos] = uid
            if ct.get_team(uid) == my_team:
                if uid != my_id:
                    friendly_bots.add(pos)
            else:
                enemy_bots.add(pos)
        self.my_pos = my_pos
        self.dir_neighbours_4 = dir_neighbours_4
        self.dir_neighbours_8 = dir_neighbours_8
        self.neighbours_4 = neighbours_4
        self.neighbours_8 = neighbours_8
        self.round = round
        self.ti = ti
        self.ax = ax
        self.scale = scale
        self.nearby_tiles = nearby_tiles
        self.enemy_bots = enemy_bots
        self.friendly_bots = friendly_bots
        self.all_bots = all_bots

    def narrow_symmetry_from_vision(self, ct):
        """
        One-shot narrowing of `symmetry_candidates` from current vision.
        Mirrors Python `narrow_symmetry_from_vision`.
        """
        if self.resolved_symmetry() is not None:
            return
        width = self.width
        height = self.height
        vision: dict[Position, tuple[Environment, bool]] = {}
        for pos in ct.get_nearby_tiles(None):
            bid = ct.get_tile_building_id(pos)
            match bid:
                case None:
                    is_core = False
                case b if b is not None:
                    is_core = ct.get_entity_type(b) == EntityType.CORE
            vision[pos] = (ct.get_tile_env(pos), is_core)
        invalid: set[Symmetry] = set()
        candidates: list[Symmetry] = list(self.symmetry_candidates)
        for sym in candidates:
            for pos, val in vision.items():
                other = vision.get(sym.action(pos, width, height))
                o = other
                if o is not None and (o != val):
                    invalid.add(sym)
                    break
        for sym in invalid:
            self.symmetry_candidates.discard(sym)

    def check_symmetry_marker(self, ct):
        """
        Mirrors Python `_check_symmetry_marker`: pin candidate set to whatever
        an allied symmetry marker in vision asserts.
        """
        if self.resolved_symmetry() is not None:
            return
        nearby = list(self.nearby_tiles)
        my_team = self.my_team
        sym = find_symmetry_marker(ct, nearby, my_team)
        if sym is not None:
            self.symmetry_candidates.clear()
            self.symmetry_candidates.add(sym)

    def resolved_symmetry(self):
        """
        Resolved symmetry iff exactly one candidate remains. Renamed from
        `symmetry` to avoid clashing with concrete units' cached `symmetry`
        field (which Python would shadow).
        """
        return (
            next(iter(self.symmetry_candidates), None)
            if len(self.symmetry_candidates) == 1
            else None
        )

    def symmetry_guess(self):
        """
        Mirroring symmetry usable even when unresolved. ROT → VER → HOR
        priority; ROT fallback if all eliminated. Mirrors Python.
        """
        for sym in [Symmetry.Rot, Symmetry.Ver, Symmetry.Hor]:
            if sym in self.symmetry_candidates:
                return sym
        return Symmetry.Rot


def in_bounds(pos, width, height):
    """
    In-bounds check shared with the trait's default `in_bounds` method. Free
    function so trait impls can call it without going through `state()` twice.
    """
    return pos.x >= 0 and pos.x < width and pos.y >= 0 and pos.y < height
