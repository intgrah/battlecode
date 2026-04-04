"""Builder state — pure data container, no methods.

All mutation is done by free functions in state_update.py and
state_update_flow.py. Helper queries (walkable, in_bounds, etc.) are
free functions in state_helpers.py.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

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

# First 4: 2 econ, 2 attack. After that: 2 attack, 1 econ repeating.
_EARLY_ROLES = (0, 0, 1, 1)  # ECON, ECON, ATTACK, ATTACK
_LATE_ROLES = (1, 1, 0)  # ATTACK, ATTACK, ECON


def _role_from_offset(dx: int, dy: int) -> int:
    idx = _OFFSET_TO_INDEX.get((dx, dy), 0)
    if idx < 4:
        return _EARLY_ROLES[idx]
    return _LATE_ROLES[(idx - 4) % len(_LATE_ROLES)]


if TYPE_CHECKING:
    from ax_chain_astar import AxChainAstar
    from bridge_astar import BridgeFlowAstar
    from flow_astar import FlowAstar
    from marker import MarkerTaskClaim


from building import (
    Building,
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

    def __init__(self, ct: Controller, core_pos: Position) -> None:
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

        # -- Per-tile arrays (indexed by y * w + x) --
        # The environment at a tile. None is unseen. Empty, Wall, Ti, Ax
        self.env: list[Environment | None] = [None] * n
        # The building at at tile. None is unseen.
        self.building: list[Building | None] = [None] * n
        # The round in which a tile was last seen.
        self.last_seen = [0] * n
        # The edge cost used for pathfinding for all in-edges to a tile
        self.cost = [COST_UNSEEN] * n
        # Passable neighbours — lazily initialized on first use
        self._pnb: list[list[int]] | None = None
        # Symmetry detection means that knowledge of the environment can be reflected.
        # Reflected tiles count as changes to the knowledge, so env, pnb
        # However, in moments such as symmetry elimination, this can cause large spikes
        # as all tiles in knowledge have to be reflected. We amortise this over multiple rounds
        # by limiting the amount we process at a time.
        self.reflect_queue: deque[int] = deque()

        # -- Resources (indexed as y * w + x) --
        self.ore_ti: set[int] = set()
        self.ore_ax: set[int] = set()
        self.blocked_ore: dict[int, int] = {}  # ore_idx → round blocked

        # -- Friendly --
        self.my_core: Position = core_pos
        self.my_core_tiles: set[int] = {
            (core_pos.y + dy) * self.w + (core_pos.x + dx)
            for dx in range(-1, 2)
            for dy in range(-1, 2)
            if 0 <= core_pos.x + dx < self.w and 0 <= core_pos.y + dy < self.h
        }
        self.my_harvesters: set[int] = set()
        self.my_barriers: set[int] = set()
        self.my_transport: set[int] = set()
        self.my_foundries: set[int] = set()
        self.my_turrets: set[int] = set()

        self.my_core_hp: int = GameConstants.CORE_MAX_HP

        # -- Enemy --
        self.en_core_pos: Position | None = None
        self.en_core_tiles: set[int] = set()
        self.en_harvesters: set[int] = set()
        self.en_barriers: set[int] = set()
        self.en_transport: set[int] = set()
        self.en_turrets: set[int] = set()
        self.enemy_bots_nearby: bool = False  # set during ephemeral update
        self.en_foundries: set[int] = set()

        # -- Both teams (unions, maintained incrementally) --
        self.harvesters: set[int] = set()
        self.barriers: set[int] = set()
        self.transport: set[int] = set()
        self.foundries: set[int] = set()
        self.turrets: set[int] = set()

        # -- Unified flow (lazily initialized) --
        self._flow: UnifiedFlow | None = None
        self._n = n

        # -- Ephemeral --
        self.unit_tiles: set[Position] = set()
        self.danger_zones: set[int] = set()
        self.claims: set[MarkerTaskClaim] = set()
        self.pos: Position = core_pos

        # -- Symmetry --
        self.symmetry: Symmetry | None = None
        self.sym_candidates: set[Symmetry] = {Symmetry.ROT, Symmetry.HOR, Symmetry.VER}

        # -- Task caches --
        self.explore_target: Position | None = None
        self.explore_radius: int = 0  # expanding ring for ECON explore
        self.rush_target_idx: int | None = None  # current rush ore target
        self.rush_target_turns: int = 0  # turns spent on current target
        self.scout_target: Position | None = None
        self.rush_cached_siege: int | None = None  # cached siege target tile
        self.rush_flow_search: object | None = None  # cached FlowAstar for extend
        self.rush_flow_source: int | None = None  # flow source for cached search

        # -- Flow search caches --
        self.ti_flow_search: FlowAstar | None = None
        self.ti_cached_source: Position | None = None
        self.ti_cached_path: list[int] | None = None
        self.ax_flow_search: AxChainAstar | None = None
        self.ax_cached_source: Position | None = None
        self.ax_cached_path: list[int] | None = None
        self.bridge_flow_search: BridgeFlowAstar | None = None
        self.bridge_cached_source: Position | None = None
        self.bridge_cached_path: list[int] | None = None

        self._nav_dist: list[int] | None = None
        self._nav_parent: list[int] | None = None
        self._nav_heuristic: list[int] | None = None
        self._nav_buckets: list[deque[int]] | None = None

        # -- Marker --
        self.last_claim: MarkerTaskClaim | None = None
        self.claim: MarkerTaskClaim | None = None

        # -- Derived beliefs --
        self.infra_max_staleness: int = 0

        # -- Flow internals --
        self.out_target: dict[int, list[int]] = {}
        self.out_target_dirty: bool = True

        # -- APSP --
        self.apsp: None = None

        # -- Landmarks --
        self.landmarks: None = None

    @property
    def pnb(self) -> list[list[int]]:
        if self._pnb is None:
            self._pnb = _init_pnb(self.w, self.h, self.w * self.h)
        return self._pnb

    @property
    def flow(self) -> UnifiedFlow:
        if self._flow is None:
            self._flow = UnifiedFlow(self._n)
        return self._flow

    @property
    def nav_dist(self) -> list[int]:
        if self._nav_dist is None:
            self._nav_dist = [INF] * self._n
        return self._nav_dist

    @property
    def nav_parent(self) -> list[int]:
        if self._nav_parent is None:
            self._nav_parent = [-1] * self._n
        return self._nav_parent

    @property
    def nav_heuristic(self) -> list[int]:
        if self._nav_heuristic is None:
            self._nav_heuristic = [-1] * self._n
        return self._nav_heuristic

    @property
    def nav_buckets(self) -> list[deque[int]]:
        if self._nav_buckets is None:
            self._nav_buckets = [deque[int]() for _ in range(DIAL_MOD)]
        return self._nav_buckets

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
        if old_passable != new_passable:
            pass  # pnb removed — A* inlines neighbor checks

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
