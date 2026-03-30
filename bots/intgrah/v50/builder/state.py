"""Builder state — pure data container, no methods.

All mutation is done by free functions in state_update.py and
state_update_flow.py. Helper queries (walkable, in_bounds, etc.) are
free functions in state_helpers.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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
from hardcode.apsp import DATA as APSP_DATA
from hardcode.apsp_loader import ApspTable
from hardcode.map import CANDIDATES, CORE_B, SYMMETRY, TILES, decode
from util import Symmetry, tiles_3x3

COST_ROAD = 2
COST_EMPTY = 10
COST_UNSEEN = 12
COST_IMPASSABLE = 1_000_000


class Economy:
    def __init__(self, n: int) -> None:
        self.ti = [0.0] * n
        self.ax = [0.0] * n
        self.rax = [0.0] * n
        self.total = [0.0] * n
        self.ti_excess = [0.0] * n
        self.ax_excess = [0.0] * n
        self.rax_excess = [0.0] * n
        self.excess = [0.0] * n
        self.blocked = [False] * n


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

        # -- Resources --
        self.ore_ti: set[Position] = set()  # derived from self.env
        self.ore_ax: set[Position] = set()  # derived from self.env

        # -- Friendly --
        self.my_core: Position = core_pos  # known from birth
        self.my_core_tiles: set[Position] = tiles_3x3(core_pos)  # known from birth
        self.my_harvesters: set[Position] = set()  # derived from self.building
        self.my_barriers: set[Position] = set()  # derived from self.buildings
        self.my_transport: set[Position] = set()  # derived from self.building
        self.my_foundries: set[Position] = set()  # derived from self.building
        self.my_turrets: set[Position] = set()  # derived from self.building
        self.my_flow = Economy(n)  # computed using state_update_econ

        self.my_core_hp: int = GameConstants.CORE_MAX_HP

        # -- Enemy --
        self.en_core_tiles: set[Position] = set()  # derived from self.building
        self.en_harvesters: set[Position] = set()  # derived from self.building
        self.en_barriers: set[Position] = set()  # derived from self.building
        self.en_transport: set[Position] = set()  # derived from self.building
        self.en_turrets: set[Position] = set()  # derived from self.building
        self.en_foundries: set[Position] = set()  # derived from self.building
        self.en_flow = Economy(n)  # computed using state_update_econ

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

        # -- Marker --
        self.last_claim: MarkerTaskClaim | None = None
        self.claim: MarkerTaskClaim | None = None

        # -- Debug --
        self.debug_target: tuple[Position, int, int, int] | None = None

        # -- Leakage mask (recomputed on reflow) --
        self.leakage_mask: list[int] | None = None

        # -- Flow internals --
        self.out_target: dict[int, list[int]] = {}
        self.out_target_dirty: bool = True

        # -- APSP --
        self.apsp: ApspTable | None = None

        # -- Load known map if available --
        _try_load_known_map(self, core_pos)

    def idx(self, x: int, y: int) -> int:
        return y * self.w + x

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.w and 0 <= y < self.h

    def is_unseen(self, x: int, y: int) -> bool:
        return self.env[y * self.w + x] is None

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


def _try_load_known_map(state: State, core_pos: Position) -> None:
    key = (state.w, state.h, core_pos)
    candidates = CANDIDATES.get(key)
    if candidates is None or len(candidates) != 1:
        return
    km = candidates[0]
    n = state.w * state.h
    tiles = decode(TILES[km](), n)
    for i in range(n):
        state.env[i] = tiles[i]
        p = Position(i % state.w, i // state.w)
        match tiles[i]:
            case Environment.ORE_TITANIUM:
                state.ore_ti.add(p)
            case Environment.ORE_AXIONITE:
                state.ore_ax.add(p)
    state.en_core_tiles = tiles_3x3(CORE_B[km])
    state.sym_candidates.clear()

    apsp_fn = APSP_DATA.get(km)
    if apsp_fn is not None:
        state.apsp = ApspTable(state.w, state.h, SYMMETRY[km], apsp_fn())
