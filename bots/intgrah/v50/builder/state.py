"""Builder state — pure data container, no methods.

All mutation is done by free functions in state_update.py and
state_update_flow.py. Helper queries (walkable, in_bounds, etc.) are
free functions in state_helpers.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections import deque

    from ax_chain_astar import AxChainAstar
    from bridge_astar import BridgeFlowAstar
    from flow_astar import FlowAstar
    from hardcode.known import KnownMap
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
from config import NAV, USE_HARDCODED_MAPS, NavMode
from hardcode.apsp import DATA as APSP_DATA
from hardcode.apsp_loader import ApspTable
from hardcode.landmarks import DATA as LANDMARK_DATA
from hardcode.map import CANDIDATES, CORE_B, SYMMETRY, TILES, decode
from util import (
    COST_EMPTY,
    COST_IMPASSABLE,
    COST_ROAD,
    COST_UNSEEN,
    Symmetry,
)


class UnifiedFlow:
    __slots__ = (
        "_edge_push",
        "_in_degree",
        "_in_rev_head",
        "_in_rev_next",
        "_in_rev_src",
        "_is_recv",
        "_out_edges",
        "_prev_all",
        "_prev_recv",
        "ax",
        "ax_excess",
        "blocked",
        "en_frac",
        "en_total",
        "excess",
        "my_frac",
        "my_total",
        "rax",
        "rax_excess",
        "ti",
        "ti_excess",
        "total",
    )

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


_DIR8 = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))


def _build_pnb(
    w: int, h: int, n: int, cost: list[int]
) -> list[list[int]]:
    pnb: list[list[int]] = [[] for _ in range(n)]
    for i in range(n):
        if cost[i] >= COST_IMPASSABLE:
            continue
        cx, cy = i % w, i // w
        for dx, dy in _DIR8:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                ni = ny * w + nx
                if cost[ni] < COST_IMPASSABLE:
                    pnb[i].append(ni)
    return pnb


def _update_pnb(
    w: int, h: int, cost: list[int], pnb: list[list[int]], i: int
) -> None:
    cx, cy = i % w, i // w
    passable = cost[i] < COST_IMPASSABLE
    pnb[i] = []
    if passable:
        for dx, dy in _DIR8:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                ni = ny * w + nx
                if cost[ni] < COST_IMPASSABLE:
                    pnb[i].append(ni)
    for dx, dy in _DIR8:
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
        n = self.w * self.h

        # -- Per-tile arrays (indexed by y * w + x) --
        self.env: list[Environment | None] = [None] * n
        self.building: list[Building | None] = [None] * n
        self.last_seen: list[int] = [0] * n
        self.cost: list[int] = [COST_UNSEEN] * n
        self.pnb: list[list[int]] = _build_pnb(self.w, self.h, n, self.cost)

        # -- Resources (indexed as y * w + x) --
        self.ore_ti: set[int] = set()
        self.ore_ax: set[int] = set()

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
        self.en_core_tiles: set[int] = set()
        self.en_harvesters: set[int] = set()
        self.en_barriers: set[int] = set()
        self.en_transport: set[int] = set()
        self.en_turrets: set[int] = set()
        self.en_foundries: set[int] = set()

        # -- Both teams (unions, maintained incrementally) --
        self.harvesters: set[int] = set()
        self.barriers: set[int] = set()
        self.transport: set[int] = set()
        self.foundries: set[int] = set()
        self.turrets: set[int] = set()

        # -- Unified flow --
        self.flow = UnifiedFlow(n)

        # -- Ephemeral --
        self.unit_tiles: set[Position] = set()
        self.claims: set[MarkerTaskClaim] = set()
        self.pos: Position = core_pos

        # -- Symmetry --
        self.symmetry: Symmetry | None = None
        self.sym_candidates: set[Symmetry] = {Symmetry.ROT, Symmetry.HOR, Symmetry.VER}

        # -- Task caches --
        self.explore_target: Position | None = None
        self.explore_radius: int = 0
        self.ti_flow_search: FlowAstar | None = None
        self.ti_cached_source: Position | None = None
        self.ti_cached_path: list[int] | None = None
        self.ax_flow_search: AxChainAstar | None = None
        self.ax_cached_source: Position | None = None
        self.ax_cached_path: list[int] | None = None
        self.bridge_flow_search: BridgeFlowAstar | None = None
        self.bridge_cached_source: Position | None = None
        self.bridge_cached_path: list[int] | None = None
        self.nav_target_key: Position | None = None
        self.nav_path: list[int] | None = None
        self.nav_dist: list[int] | None = None
        self.nav_parent: list[int] | None = None
        self.nav_ht: list[int] | None = None
        self.nav_bk: list[deque[int]] | None = None
        self.nav_touched: list[int] = []

        # -- Marker --
        self.last_claim: MarkerTaskClaim | None = None
        self.claim: MarkerTaskClaim | None = None

        # -- Derived beliefs --
        self.infra_max_staleness: int = 0

        # -- Leakage mask (recomputed on reflow) --
        self.leakage_mask: list[int] | None = None

        # -- Flow internals --
        self.out_target: dict[int, list[int]] = {}
        self.out_target_dirty: bool = True

        # -- APSP --
        self.apsp: ApspTable | None = None

        # -- Landmarks --
        self.landmarks: tuple[list[int], int, bytes] | None = None

        # -- HPA* --
        self.hpa_graph: object | None = None

        km = _try_identify_map(self, core_pos)
        if km is not None:
            if USE_HARDCODED_MAPS:
                _load_map_tiles(self, km)
            if NAV == NavMode.ASTAR_APSP:
                _load_apsp(self, km)
            if NAV == NavMode.ASTAR_LANDMARKS:
                _load_landmarks(self, km)

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
            case Environment.WALL | Environment.ORE_TITANIUM | Environment.ORE_AXIONITE:
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
            _update_pnb(self.w, self.h, self.cost, self.pnb, i)

    def walkable(self, x: int, y: int) -> int:
        if Position(x, y) in self.unit_tiles:
            return COST_IMPASSABLE
        i = y * self.w + x
        match self.env[i]:
            case None:
                return COST_UNSEEN
            case Environment.WALL | Environment.ORE_TITANIUM | Environment.ORE_AXIONITE:
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


def _try_identify_map(state: State, core_pos: Position) -> KnownMap | None:
    key = (state.w, state.h, core_pos)
    candidates = CANDIDATES.get(key)
    if candidates is None or len(candidates) != 1:
        return None
    return candidates[0]


def _load_map_tiles(state: State, km: KnownMap) -> None:
    n = state.w * state.h
    tiles = decode(TILES[km](), n)
    for i in range(n):
        state.env[i] = tiles[i]
        state.update_cost(i)
        match tiles[i]:
            case Environment.ORE_TITANIUM:
                state.ore_ti.add(i)
            case Environment.ORE_AXIONITE:
                state.ore_ax.add(i)
    cb = CORE_B[km]
    w = state.w
    state.en_core_tiles = {
        (cb.y + dy) * w + (cb.x + dx)
        for dx in range(-1, 2)
        for dy in range(-1, 2)
        if 0 <= cb.x + dx < w and 0 <= cb.y + dy < state.h
    }
    state.sym_candidates.clear()


def _load_apsp(state: State, km: KnownMap) -> None:
    apsp_fn = APSP_DATA.get(km)
    if apsp_fn is not None:
        state.apsp = ApspTable(state.w, state.h, SYMMETRY[km], apsp_fn())


def _load_landmarks(state: State, km: KnownMap) -> None:
    lm_fn = LANDMARK_DATA.get(km)
    if lm_fn is not None:
        state.landmarks = lm_fn()
