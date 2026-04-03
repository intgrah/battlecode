"""Builder state — pure data container."""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

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
    Role,
    Symmetry,
)

if TYPE_CHECKING:
    from marker import MarkerChainPlan, MarkerClaim


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
        self.ti: list[float] = [0.0] * n
        self.ax: list[float] = [0.0] * n
        self.rax: list[float] = [0.0] * n
        self.total: list[float] = [0.0] * n
        self.my_frac: list[float] = [0.0] * n
        self.en_frac: list[float] = [0.0] * n
        self.my_total: list[float] = [0.0] * n
        self.en_total: list[float] = [0.0] * n
        self.ti_excess: list[float] = [0.0] * n
        self.ax_excess: list[float] = [0.0] * n
        self.rax_excess: list[float] = [0.0] * n
        self.excess: list[float] = [0.0] * n
        self.blocked: list[bool] = [False] * n

        self._in_degree: list[int] = [0] * n
        self._is_recv: list[bool] = [False] * n
        self._in_rev_head: list[int] = [-1] * n
        max_scratch = n * 8
        self._in_rev_next: list[int] = [0] * max_scratch
        self._in_rev_src: list[int] = [0] * max_scratch
        self._edge_push: list[float] = [0.0] * max_scratch
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
    by free functions in state_update.py, not methods.
    """

    def __init__(self, ct: Controller, core_pos: Position) -> None:
        self.w: int = ct.get_map_width()
        self.h: int = ct.get_map_height()
        self.my_team = ct.get_team()
        self.birthday: int = ct.get_current_round()
        self.age: int = 0
        n = self.w * self.h

        # Per-tile arrays (indexed by y * w + x)
        self.env: list[Environment | None] = [None] * n
        self.building: list[Building | None] = [None] * n
        self.last_seen: list[int] = [0] * n
        self.cost: list[int] = [COST_UNSEEN] * n
        self.pnb: list[list[int]] = _init_pnb(self.w, self.h, n)
        self.reflect_queue: deque[int] = deque()

        # Resources
        self.ore_ti: set[int] = set()
        self.ore_ax: set[int] = set()
        self.blocked_ore: set[int] = set()

        # Friendly
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

        # Enemy
        self.en_core_pos: Position | None = None
        self.en_core_tiles: set[int] = set()
        self.en_harvesters: set[int] = set()
        self.en_barriers: set[int] = set()
        self.en_transport: set[int] = set()
        self.en_foundries: set[int] = set()
        self.en_turrets: set[int] = set()

        # Both teams (unions, maintained incrementally)
        self.harvesters: set[int] = set()
        self.barriers: set[int] = set()
        self.transport: set[int] = set()
        self.foundries: set[int] = set()
        self.turrets: set[int] = set()

        # Unified flow
        self.flow: UnifiedFlow = UnifiedFlow(n)

        # Role
        self.role: Role = Role.ECON

        # Symmetry
        self.symmetry: Symmetry | None = None
        self.sym_candidates: set[Symmetry] = {Symmetry.ROT, Symmetry.HOR, Symmetry.VER}

        # Ephemeral (cleared each turn)
        self.unit_tiles: set[Position] = set()
        self.danger_zones: set[int] = set()
        self.claims: set[MarkerClaim] = set()
        self.chain_claims: set[MarkerChainPlan] = set()
        self.pos: Position = core_pos

        # Navigation (A* / Dial's)
        self.nav_dist: list[int] = [INF] * n
        self.nav_parent: list[int] = [-1] * n
        self.nav_heuristic: list[int] = [-1] * n
        self.nav_buckets: list[deque[int]] = [deque() for _ in range(DIAL_MOD)]

        # Exploration
        self.explore_target: Position | None = None

        # Marker claims
        self.last_claim: MarkerClaim | None = None
        self.claim: MarkerClaim | None = None

        # Rush state
        self.rush_siege_target: int | None = None

        # Derived beliefs
        self.infra_max_staleness: int = 0

        # Flow internals
        self.out_target: dict[int, list[int]] = {}
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
                if self.building[i] is None:
                    self.cost[i] = COST_EMPTY
                else:
                    self.cost[i] = COST_ROAD
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
