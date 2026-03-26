"""Builder state — pure data container, no methods.

All mutation is done by free functions in state_update.py and
state_update_flow.py. Helper queries (walkable, in_bounds, etc.) are
free functions in state_helpers.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ax_chain_astar import AxChainAstar
    from bridge_astar import BridgeFlowAstar
    from flow_astar import FlowAstar
    from marker import TaskClaim
    from nav_astar import NavAstar

from cambc import Controller, Direction, EntityType, Environment, Position, Team
from known_maps import MAPS
from known_maps import decode as decode_known_map
from util import WALKABLE_BUILDINGS, tiles_3x3

COST_ROAD = 2
COST_EMPTY = 10
COST_UNSEEN = 12
COST_IMPASSABLE = 1_000_000


@dataclass(slots=True)
class FlowState:
    n: int
    ti: list[float] = field(init=False)
    ax: list[float] = field(init=False)
    rax: list[float] = field(init=False)
    total: list[float] = field(init=False)
    ti_excess: list[float] = field(init=False)
    ax_excess: list[float] = field(init=False)
    rax_excess: list[float] = field(init=False)
    excess: list[float] = field(init=False)
    blocked: list[bool] = field(init=False)

    def __post_init__(self) -> None:
        n = self.n
        self.ti = [0.0] * n
        self.ax = [0.0] * n
        self.rax = [0.0] * n
        self.total = [0.0] * n
        self.ti_excess = [0.0] * n
        self.ax_excess = [0.0] * n
        self.rax_excess = [0.0] * n
        self.excess = [0.0] * n
        self.blocked = [False] * n


class Symmetry(Enum):
    """Map symmetry type. Maps are guaranteed to have at least one.

    Any two symmetries imply the third, so either exactly one holds
    or all three hold. Exactly two is impossible.
    """

    ROT = auto()
    HOR = auto()
    VER = auto()


class State:
    """Pure data container for builder belief state.

    Initialised once per builder. All fields are public. Mutation is done
    by free functions (state_update, state_update_flow), not methods.
    """

    def __init__(self, ct: Controller, core_pos: tuple[int, int]) -> None:
        self.w = ct.get_map_width()
        self.h = ct.get_map_height()
        self.my_team = ct.get_team()
        self.age = 0
        n = self.w * self.h

        # -- Per-tile arrays (indexed by y * w + x) --
        self.env: list[Environment | None] = [None] * n
        self.entity: list[tuple[EntityType, Team] | None] = [None] * n
        self.direction: list[Direction | None] = [None] * n
        self.bridge_target: list[tuple[int, int] | None] = [None] * n
        self.last_seen: list[int] = [0] * n

        # -- Resources --
        self.ore_ti: set[tuple[int, int]] = set()
        self.ore_ax: set[tuple[int, int]] = set()

        # -- Friendly --
        self.my_core: tuple[int, int] = core_pos
        self.my_core_tiles: set[int] = tiles_3x3(*core_pos, self.w, self.h)
        self.my_harvested: set[tuple[int, int]] = set()
        self.my_harvesters: set[int] = set()
        self.my_transport: set[int] = set()
        self.my_foundries: set[int] = set()
        self.my_turrets: set[int] = set()
        self.my_flow = FlowState(n)

        self.my_core_hp: int = 500
        self.my_core_max_hp: int = 500
        self.my_barriers: set[int] = set()

        # -- Enemy --
        self.en_core: tuple[int, int] | None = None
        self.en_core_tiles: set[int] = set()
        self.en_harvested: set[tuple[int, int]] = set()
        self.en_harvesters: set[int] = set()
        self.en_barriers: set[int] = set()
        self.en_transport: set[int] = set()
        self.en_turrets: set[int] = set()
        self.en_foundries: set[int] = set()
        self.en_flow = FlowState(n)

        # -- Ephemeral --
        self.unit_tiles: set[int] = set()
        self.claims: set[TaskClaim] = set()
        self.pos: Position = Position(core_pos[0], core_pos[1])

        # -- Symmetry --
        self.symmetry: Symmetry | None = None
        self.sym_candidates: set[Symmetry] = {Symmetry.ROT, Symmetry.HOR, Symmetry.VER}

        # -- Task caches --
        self.explore_target: Position | None = None
        self.explore_radius: int = 0
        self.ti_flow_search: FlowAstar | None = None
        self.ti_cached_source: tuple[int, int] | None = None
        self.ti_cached_path: list[int] | None = None
        self.ax_flow_search: AxChainAstar | None = None
        self.ax_cached_source: tuple[int, int] | None = None
        self.ax_cached_path: list[int] | None = None
        self.bridge_flow_search: BridgeFlowAstar | None = None
        self.bridge_cached_source: tuple[int, int] | None = None
        self.bridge_cached_path: list[int] | None = None
        self.nav_target_key: tuple[int, int] | None = None
        self.nav_search: NavAstar | None = None
        self.nav_path: list[int] | None = None

        # -- Marker --
        self.last_claim: TaskClaim | None = None
        self.claim: TaskClaim | None = None

        # -- Debug --
        self.debug_target: tuple[Position, int, int, int] | None = None

        # -- Leakage mask (recomputed on reflow) --
        self.leakage_mask: list[int] | None = None

        # -- Flow internals --
        self.out_target: dict[int, list[int]] = {}
        self.out_target_dirty: bool = True

        # -- Load known map if available --
        _try_load_known_map(self, core_pos)

    def idx(self, x: int, y: int) -> int:
        return y * self.w + x

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.w and 0 <= y < self.h

    def is_unseen(self, x: int, y: int) -> bool:
        return self.env[y * self.w + x] is None

    def walkable(self, x: int, y: int) -> int:
        i = y * self.w + x
        if i in self.unit_tiles:
            return COST_IMPASSABLE
        match self.env[i]:
            case None:
                return COST_UNSEEN
            case Environment.WALL | Environment.ORE_TITANIUM | Environment.ORE_AXIONITE:
                return COST_IMPASSABLE
        match self.entity[i]:
            case None:
                return COST_EMPTY
            case (EntityType.MARKER, _):
                return COST_EMPTY
            case (EntityType.CORE, team) if team == self.my_team:
                return COST_ROAD
            case (etype, _) if etype in WALKABLE_BUILDINGS:
                return COST_ROAD
            case _:
                return COST_IMPASSABLE


def _try_load_known_map(state: State, core_pos: tuple[int, int]) -> None:
    key = (state.w, state.h, core_pos[0], core_pos[1])
    known = MAPS.get(key)
    if known is None:
        return
    encoded, en_core = known
    tiles = decode_known_map(encoded, state.w * state.h)
    for i in range(state.w * state.h):
        state.env[i] = tiles[i]
        x, y = i % state.w, i // state.w
        match tiles[i]:
            case Environment.ORE_TITANIUM:
                state.ore_ti.add((x, y))
            case Environment.ORE_AXIONITE:
                state.ore_ax.add((x, y))
    state.en_core = en_core
    state.en_core_tiles = tiles_3x3(*en_core, state.w, state.h)
    state.sym_candidates.clear()
