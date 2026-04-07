"""Builder state -- pure data container, no methods.

All mutation is done by free functions in state_update.py.
Helper queries (walkable, in_bounds, etc.) are free functions
in state_helpers.py.

Simplified from rush: NO flow simulation, NO pnb, NO nav arrays.
We track connected harvesters and transport sets but don't compute
flow magnitudes.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from marker import MarkerTaskClaim
    from navigation.grid import PassableGrid
    from navigation.nav_bfs import NavBfs

from building import (
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingCore,
    BuildingMarker,
    BuildingRoad,
    BuildingSplitter,
)
from cambc import (
    Controller,
    Environment,
    GameConstants,
    Position,
)
from core import role_for_spawn
from util import (
    COST_EMPTY,
    COST_IMPASSABLE,
    COST_ROAD,
    COST_UNSEEN,
    Symmetry,
)

# Direction offset -> spawn index (0-based, clockwise from N)
_OFFSET_TO_INDEX: dict[tuple[int, int], int] = {
    (0, -1): 0,
    (1, -1): 1,
    (1, 0): 2,
    (1, 1): 3,
    (0, 1): 4,
    (-1, 1): 5,
    (-1, 0): 6,
    (-1, -1): 7,
}


class State:
    """Pure data container for builder belief state.

    Initialised once per builder. All fields are public. Mutation is done
    by free functions in state_update.py, not methods.
    """

    @classmethod
    def prealloc_max(cls) -> State:
        """Pre-allocate for max 50x50 map. Called in Player.__init__ (5s budget)."""
        s = object.__new__(cls)
        n = 50 * 50
        s.w = 50
        s.h = 50
        s._n = n

        # Heavy arrays
        s.env = [None] * n
        s.building = [None] * n
        s.last_seen = [0] * n
        s.cost = [COST_UNSEEN] * n

        # Grid / nav -- set by Player.__init__ after map size known
        s.grid: PassableGrid | None = None
        s.nav_bfs: NavBfs | None = None

        # Symmetry
        s.reflect_queue: deque[int] = deque()
        s.symmetry: Symmetry | None = None
        s.sym_candidates: set[Symmetry] = {Symmetry.ROT, Symmetry.HOR, Symmetry.VER}

        # Resources
        s.ore_ti: set[int] = set()
        s.ore_ax: set[int] = set()
        s.blocked_ore: dict[int, int] = {}

        # Friendly
        s.my_harvesters: set[int] = set()
        s.my_transport: set[int] = set()
        s.my_turrets: set[int] = set()
        s.my_core_hp: int = GameConstants.CORE_MAX_HP

        # Enemy
        s.en_core_pos: Position | None = None
        s.en_core_tiles: set[int] = set()
        s.en_harvesters: set[int] = set()
        s.en_transport: set[int] = set()
        s.en_turrets: set[int] = set()
        s.en_barriers: set[int] = set()
        s.en_foundries: set[int] = set()

        # Both teams (unions, maintained incrementally)
        s.harvesters: set[int] = set()
        s.transport: set[int] = set()
        s.turrets: set[int] = set()
        s.foundries: set[int] = set()
        s.barriers: set[int] = set()

        # Connectivity (no flow magnitudes)
        s.connected_harvesters: set[int] = set()
        s._chain_search: object | None = None
        s._chain_source: int | None = None
        s._chain_path: list[int] | None = None
        s._chain_cursor: int = 0
        s._my_placed_harvesters: set[int] = set()

        # Ephemeral
        s.unit_tiles: set[Position] = set()
        s.danger_zones: set[int] = set()
        s.claims: set[MarkerTaskClaim] = set()
        s.enemy_bots_nearby: bool = False

        # Exploration
        s.explore_target: Position | None = None
        s.explore_radius: int = 0

        # Marker / claim
        s.last_claim: MarkerTaskClaim | None = None
        s.claim: MarkerTaskClaim | None = None

        # Derived beliefs
        s.infra_max_staleness: int = 0
        s.out_target_dirty: bool = True

        # Position (set properly in __init__ and each update)
        s.pos: Position = Position(0, 0)

        return s

    def __init__(
        self,
        ct: Controller,
        core_pos: Position,
        pre: State | None = None,
    ) -> None:
        # ct-dependent init (must happen in run() budget)
        self.w = ct.get_map_width()
        self.h = ct.get_map_height()
        self.my_team = ct.get_team()
        self.birthday = ct.get_current_round()
        self.age = 0
        n = self.w * self.h
        self._n = n
        self.my_core: Position = core_pos
        self.my_core_tiles: set[int] = {
            (core_pos.y + dy) * self.w + (core_pos.x + dx)
            for dx in range(-1, 2)
            for dy in range(-1, 2)
            if 0 <= core_pos.x + dx < self.w and 0 <= core_pos.y + dy < self.h
        }
        self.pos: Position = core_pos

        # Role assignment via spawn offset
        spawn_pos = ct.get_position()
        dx = spawn_pos.x - core_pos.x
        dy = spawn_pos.y - core_pos.y
        idx = _OFFSET_TO_INDEX.get((dx, dy), 0)
        self.role: int = role_for_spawn(idx)

        if pre is not None:
            # Reuse pre-allocated arrays
            self.env = pre.env
            self.building = pre.building
            self.last_seen = pre.last_seen
            self.cost = pre.cost
            self.grid = pre.grid
            self.nav_bfs = pre.nav_bfs
            self.reflect_queue = pre.reflect_queue
            self.symmetry = pre.symmetry
            self.sym_candidates = pre.sym_candidates
            self.ore_ti = pre.ore_ti
            self.ore_ax = pre.ore_ax
            self.blocked_ore = pre.blocked_ore
            self.my_harvesters = pre.my_harvesters
            self.my_transport = pre.my_transport
            self.my_turrets = pre.my_turrets
            self.my_core_hp = pre.my_core_hp
            self.en_core_pos = pre.en_core_pos
            self.en_core_tiles = pre.en_core_tiles
            self.en_harvesters = pre.en_harvesters
            self.en_transport = pre.en_transport
            self.en_turrets = pre.en_turrets
            self.en_barriers = pre.en_barriers
            self.en_foundries = pre.en_foundries
            self.harvesters = pre.harvesters
            self.transport = pre.transport
            self.turrets = pre.turrets
            self.foundries = pre.foundries
            self.barriers = pre.barriers
            self.connected_harvesters = pre.connected_harvesters
            self._chain_search = pre._chain_search
            self._chain_source = pre._chain_source
            self._chain_path = pre._chain_path
            self._chain_cursor = pre._chain_cursor
            self._my_placed_harvesters = pre._my_placed_harvesters
            self.unit_tiles = pre.unit_tiles
            self.danger_zones = pre.danger_zones
            self.claims = pre.claims
            self.enemy_bots_nearby = pre.enemy_bots_nearby
            self.explore_target = pre.explore_target
            self.explore_radius = pre.explore_radius
            self.last_claim = pre.last_claim
            self.claim = pre.claim
            self.infra_max_staleness = pre.infra_max_staleness
            self.out_target_dirty = pre.out_target_dirty
        else:
            # Fresh allocation (no prealloc available)
            self.env: list[Environment | None] = [None] * n
            self.building = [None] * n
            self.last_seen = [0] * n
            self.cost = [COST_UNSEEN] * n
            self.grid = None
            self.nav_bfs = None
            self.reflect_queue: deque[int] = deque()
            self.symmetry: Symmetry | None = None
            self.sym_candidates: set[Symmetry] = {
                Symmetry.ROT,
                Symmetry.HOR,
                Symmetry.VER,
            }
            self.ore_ti: set[int] = set()
            self.ore_ax: set[int] = set()
            self.blocked_ore: dict[int, int] = {}
            self.my_harvesters: set[int] = set()
            self.my_transport: set[int] = set()
            self.my_turrets: set[int] = set()
            self.my_core_hp: int = GameConstants.CORE_MAX_HP
            self.en_core_pos: Position | None = None
            self.en_core_tiles: set[int] = set()
            self.en_harvesters: set[int] = set()
            self.en_transport: set[int] = set()
            self.en_turrets: set[int] = set()
            self.en_barriers: set[int] = set()
            self.en_foundries: set[int] = set()
            self.harvesters: set[int] = set()
            self.transport: set[int] = set()
            self.turrets: set[int] = set()
            self.foundries: set[int] = set()
            self.barriers: set[int] = set()
            self.connected_harvesters: set[int] = set()
            self._my_placed_harvesters: set[int] = set()
            self._chain_search: object | None = None
            self._chain_source: int | None = None
            self._chain_path: list[int] | None = None
            self.unit_tiles: set[Position] = set()
            self.danger_zones: set[int] = set()
            self.claims: set[MarkerTaskClaim] = set()
            self.enemy_bots_nearby: bool = False
            self.explore_target: Position | None = None
            self.explore_radius: int = 0
            self.last_claim = None
            self.claim = None
            self.infra_max_staleness: int = 0
            self.out_target_dirty: bool = True

    def idx(self, x: int, y: int) -> int:
        return y * self.w + x

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.w and 0 <= y < self.h

    def is_unseen(self, x: int, y: int) -> bool:
        return self.env[y * self.w + x] is None

    def update_cost(self, i: int) -> None:
        old_passable = self.cost[i] < COST_IMPASSABLE
        match self.env[i]:
            case None:
                self.cost[i] = COST_UNSEEN
            case Environment.WALL:
                self.cost[i] = COST_IMPASSABLE
            case Environment.ORE_TITANIUM | Environment.ORE_AXIONITE:
                match self.building[i]:
                    case None | BuildingMarker():
                        self.cost[i] = COST_EMPTY
                    case (
                        BuildingRoad()
                        | BuildingConveyor()
                        | BuildingArmouredConveyor()
                        | BuildingSplitter()
                        | BuildingBridge()
                    ):
                        self.cost[i] = COST_ROAD
                    case _:
                        self.cost[i] = COST_IMPASSABLE
            case _:
                match self.building[i]:
                    case None | BuildingMarker():
                        self.cost[i] = COST_EMPTY
                    case BuildingCore(team) if team == self.my_team:
                        self.cost[i] = COST_ROAD
                    case (
                        BuildingRoad()
                        | BuildingConveyor()
                        | BuildingArmouredConveyor()
                        | BuildingSplitter()
                        | BuildingBridge()
                    ):
                        self.cost[i] = COST_ROAD
                    case _:
                        self.cost[i] = COST_IMPASSABLE
        new_passable = self.cost[i] < COST_IMPASSABLE
        if old_passable != new_passable and self.grid is not None:
            self.grid.set_passable(i, passable=new_passable)

    def walkable(self, x: int, y: int) -> int:
        if Position(x, y) in self.unit_tiles:
            return COST_IMPASSABLE
        i = y * self.w + x
        match self.env[i]:
            case None:
                return COST_UNSEEN
            case Environment.WALL:
                return COST_IMPASSABLE
        match self.building[i]:
            case None | BuildingMarker():
                return COST_EMPTY
            case BuildingCore(team) if team == self.my_team:
                return COST_ROAD
            case (
                BuildingRoad()
                | BuildingConveyor()
                | BuildingArmouredConveyor()
                | BuildingSplitter()
                | BuildingBridge()
            ):
                return COST_ROAD
            case _:
                return COST_IMPASSABLE
