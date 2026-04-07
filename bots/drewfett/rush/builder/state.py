"""Builder state — pure data container, no methods.

All mutation is done by free functions in state_update.py and
state_update_flow.py. Helper queries (walkable, in_bounds, etc.) are
free functions in state_helpers.py.
"""

from __future__ import annotations

from collections import deque

# Roles: ECON=0, ATTACK=1, DEFENSE=2
# Direction offset → spawn direction index (0-7), wraps for 8+
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

# First 4: 3 econ, 1 attack. After that: attack, econ repeating.
_EARLY_ROLES = (0, 0, 0, 1)  # ECON, ECON, ECON, ATTACK
_LATE_ROLES = (1, 0)  # ATTACK, ECON


def _role_from_offset(dx: int, dy: int) -> int:
    idx = _OFFSET_TO_INDEX.get((dx, dy), 0)
    if idx < 4:
        return _EARLY_ROLES[idx]
    return _LATE_ROLES[(idx - 4) % len(_LATE_ROLES)]


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
from util import (
    COST_EMPTY,
    COST_IMPASSABLE,
    COST_ROAD,
    COST_UNSEEN,
    DIAL_MOD,
    DIR8_DELTA,
    INF,
    Symmetry,
)


class UnifiedFlow:
    def __init__(self, n: int) -> None:
        self.ti = [0.0] * n
        self.ax = [0.0] * n
        self.rax = [0.0] * n
        self.total = [0.0] * n
        self.my_frac = [0.0] * n
        self.en_frac = [0.0] * n
        self.my_total = [0.0] * n
        self.en_total = [0.0] * n
        self.ti_excess = [0.0] * n
        self.ax_excess = [0.0] * n
        self.rax_excess = [0.0] * n
        self.excess = [0.0] * n
        self.blocked = [False] * n
        self.gunners_fed = [
            0.0
        ] * n  # committed Ti/round downstream (gunner=0.2, sentinel≈0.33)

        # Internally allocated lists to avoid re-allocating
        self._in_degree = [0] * n
        self._is_recv = [False] * n
        self._in_rev_head = [-1] * n
        max_scratch = n * 8
        self._in_rev_next = [0] * max_scratch
        self._in_rev_src = [0] * max_scratch
        self._edge_push = [0.0] * max_scratch
        self._out_edges: list[list[tuple[int, int]]] = [[] for _ in range(n)]
        self._prev_all: tuple[list[int], ...] = ()
        self._prev_recv: tuple[list[int], ...] = ()


def _init_pnb(w: int, h: int, n: int) -> list[list[int]]:
    pnb: list[list[int]] = [[] for _ in range(n)]
    for i in range(n):
        cx, cy = i % w, i // w
        for dx, dy in DIR8_DELTA:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                pnb[i].append(ny * w + nx)
    return pnb


def _update_pnb(w: int, h: int, cost: list[int], pnb: list[list[int]], i: int) -> None:
    cx, cy = i % w, i // w
    passable = cost[i] < COST_IMPASSABLE
    pnb[i] = []
    if passable:
        for dx, dy in DIR8_DELTA:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                ni = ny * w + nx
                if cost[ni] < COST_IMPASSABLE:
                    pnb[i].append(ni)
    for dx, dy in DIR8_DELTA:
        nx, ny = cx + dx, cy + dy
        if 0 <= nx < w and 0 <= ny < h:
            ni = ny * w + nx
            if cost[ni] >= COST_IMPASSABLE:
                continue
            nb_list = pnb[ni]
            if passable:
                if i not in nb_list:
                    nb_list.append(i)
            elif i in nb_list:
                nb_list.remove(i)


class State:
    """Pure data container for builder belief state.

    Initialised once per builder. All fields are public. Mutation is done
    by free functions (state_update, state_update_flow), not methods.
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
        s.pnb = _init_pnb(50, 50, n)
        s.flow = UnifiedFlow(n)
        s.nav_dist = [INF] * n
        s.nav_parent = [-1] * n
        s.nav_heuristic = [-1] * n
        s.nav_buckets = [deque[int]() for _ in range(DIAL_MOD)]
        s._nav_gen = bytearray(n)
        s._nav_g = 1
        # All the lightweight fields
        s.reflect_queue = deque()
        s.ore_ti = set()
        s.ore_ax = set()
        s.blocked_ore = {}
        s.my_harvesters = set()
        s.my_barriers = set()
        s.my_transport = set()
        s.my_foundries = set()
        s.my_turrets = set()
        s.my_core_hp = GameConstants.CORE_MAX_HP
        s.en_core_pos = None
        s.en_core_tiles = set()
        s.en_harvesters = set()
        s.en_barriers = set()
        s.en_transport = set()
        s.en_turrets = set()
        s.enemy_bots_nearby = False
        s.en_foundries = set()
        s.harvesters = set()
        s.barriers = set()
        s.transport = set()
        s.foundries = set()
        s.turrets = set()
        s.unit_tiles = set()
        s.danger_zones = set()
        s.claims = set()
        s.symmetry = None
        s.sym_candidates = {Symmetry.ROT, Symmetry.HOR, Symmetry.VER}
        s.explore_target = None
        s.explore_radius = 0
        s.rush_target_idx = None
        s.rush_target_turns = 0
        s.scout_target = None
        s.rush_cached_siege = None
        s.rush_flow_search = None
        s.rush_flow_source = None
        s.ti_flow_search = None
        s.ti_cached_source = None
        s.ti_cached_path = None
        s.ax_flow_search = None
        s.ax_cached_source = None
        s.ax_cached_path = None
        s.bridge_flow_search = None
        s.bridge_cached_source = None
        s.bridge_cached_path = None
        s.last_claim = None
        s.claim = None
        s.infra_max_staleness = 0
        s.out_target = {}
        s.out_target_dirty = True
        s.apsp = None
        s.landmarks = None
        s.grid = None  # set by Player.__init__
        s.nav_bfs = None  # set by Player.__init__
        return s

    def __init__(
        self, ct: Controller, core_pos: Position, pre: State | None = None
    ) -> None:
        # ct-dependent init (must happen in run() budget)
        self.w = ct.get_map_width()
        self.h = ct.get_map_height()
        self.my_team = ct.get_team()
        self.birthday = ct.get_current_round()
        self.age = 0
        spawn_pos = ct.get_position()
        dx = spawn_pos.x - core_pos.x
        dy = spawn_pos.y - core_pos.y
        self.role: int = _role_from_offset(dx, dy)
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

        # Reuse pre-allocated arrays
        assert pre is not None
        self.env = pre.env
        self.building = pre.building
        self.last_seen = pre.last_seen
        self.cost = pre.cost
        self.flow = pre.flow
        self.nav_dist = pre.nav_dist
        self.nav_parent = pre.nav_parent
        self.nav_heuristic = pre.nav_heuristic
        self.nav_buckets = pre.nav_buckets
        self._nav_gen = pre._nav_gen
        self._nav_g = pre._nav_g
        # pnb indices depend on width — rebuild if map size differs from prealloc
        if self.w == 50 and self.h == 50:
            self.pnb = pre.pnb
        else:
            self.pnb = _init_pnb(self.w, self.h, n)
        self.reflect_queue = pre.reflect_queue
        self.ore_ti = pre.ore_ti
        self.ore_ax = pre.ore_ax
        self.blocked_ore = pre.blocked_ore
        self.my_harvesters = pre.my_harvesters
        self.my_barriers = pre.my_barriers
        self.my_transport = pre.my_transport
        self.my_foundries = pre.my_foundries
        self.my_turrets = pre.my_turrets
        self.my_core_hp = pre.my_core_hp
        self.en_core_pos = pre.en_core_pos
        self.en_core_tiles = pre.en_core_tiles
        self.en_harvesters = pre.en_harvesters
        self.en_barriers = pre.en_barriers
        self.en_transport = pre.en_transport
        self.en_turrets = pre.en_turrets
        self.enemy_bots_nearby = pre.enemy_bots_nearby
        self.en_foundries = pre.en_foundries
        self.harvesters = pre.harvesters
        self.barriers = pre.barriers
        self.transport = pre.transport
        self.foundries = pre.foundries
        self.turrets = pre.turrets
        self.unit_tiles = pre.unit_tiles
        self.danger_zones = pre.danger_zones
        self.claims = pre.claims
        self.symmetry = pre.symmetry
        self.sym_candidates = pre.sym_candidates
        self.explore_target = pre.explore_target
        self.explore_radius = pre.explore_radius
        self.rush_target_idx = pre.rush_target_idx
        self.rush_target_turns = pre.rush_target_turns
        self.scout_target = pre.scout_target
        self.rush_cached_siege = pre.rush_cached_siege
        self.rush_flow_search = pre.rush_flow_search
        self.rush_flow_source = pre.rush_flow_source
        self.ti_flow_search = pre.ti_flow_search
        self.ti_cached_source = pre.ti_cached_source
        self.ti_cached_path = pre.ti_cached_path
        self.ax_flow_search = pre.ax_flow_search
        self.ax_cached_source = pre.ax_cached_source
        self.ax_cached_path = pre.ax_cached_path
        self.bridge_flow_search = pre.bridge_flow_search
        self.bridge_cached_source = pre.bridge_cached_source
        self.bridge_cached_path = pre.bridge_cached_path
        self.last_claim = pre.last_claim
        self.claim = pre.claim
        self.infra_max_staleness = pre.infra_max_staleness
        self.out_target = pre.out_target
        self.out_target_dirty = pre.out_target_dirty
        self.apsp = pre.apsp
        self.landmarks = pre.landmarks
        self.grid = pre.grid
        self.nav_bfs = pre.nav_bfs

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
