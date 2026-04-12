from __future__ import annotations

from collections import deque
from random import Random
from typing import TYPE_CHECKING

from building import (
    Building,
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingRoad,
    BuildingSplitter,
)
from cambc import Controller, EntityType, Environment, Position
from util import INF, Symmetry

from .algorithms.nav_bfs import NavBfs, PassableGrid

if TYPE_CHECKING:
    from .role import Role

__all__ = ["State"]

WALKABLE_ENTITIES = [
    EntityType.CONVEYOR,
    EntityType.ROAD,
    EntityType.SPLITTER,
    EntityType.ARMOURED_CONVEYOR,
    EntityType.BRIDGE,
]


class State:
    @staticmethod
    def find_core(ct: Controller) -> Position:
        my_team = ct.get_team()
        for bid in ct.get_nearby_buildings():
            if (
                ct.get_team(bid) == my_team
                and ct.get_entity_type(bid) == EntityType.CORE
            ):
                return ct.get_position(bid)
        msg = "Core not visible at spawn"
        raise RuntimeError(msg)

    def __init__(self, ct: Controller) -> None:
        self.w = ct.get_map_width()
        self.h = ct.get_map_height()
        self.my_team = ct.get_team()
        self.my_core: Position = State.find_core(ct)
        self.rng = Random(ct.get_id())
        w, h = self.w, self.h
        n = w * h

        # Padded cost-grid dimensions. A 3-tile border on every side
        # gives A* unconditional neighbor lookups for the bridge
        # r²≤9 set — any out-of-bounds neighbor lands on the padding
        # which is permanently INF, so the inner loop drops bounds
        # checks entirely. Only `cost_grid` and `conveyor_cost_grid`
        # use the padded layout; env/buildings/hp/... stay real-sized.
        self.pad: int = 3
        self.pw: int = w + 2 * self.pad
        self.ph: int = h + 2 * self.pad
        pn = self.pw * self.ph

        # Per-tile arrays (indexed by y * w + x)
        self.env: list[Environment | None] = [None] * n
        self.buildings: list[Building | None] = [None] * n
        self.hp: list[int] = [0] * n
        self.max_hp: list[int] = [0] * n
        # Padded cost grids: border = INF, interior initialised to
        # the default cost for an unseen tile. Real tile (x, y) lives
        # at padded index (y + pad) * pw + (x + pad).
        self.cost_grid: list[int] = [INF] * pn
        self.conveyor_cost_grid: list[int] = [INF] * pn
        self._init_pad_interior()
        # Per-bot adgato-style passability grid + BFS navigator for
        # movement. Shared across all `move_search` calls for this
        # bot (which is why NavBfs lives on State, not at module
        # level like v54's old AStarSearch singletons).
        self.pass_grid: PassableGrid = PassableGrid(w, h)
        self.nav: NavBfs = NavBfs(self.pass_grid)
        self.belt_load_counts = [0] * n
        self.line_load_counts = [0] * n
        self.line_loads_computed = [False] * n
        self.conveyors_to_here: list[list[Position]] = [[] for _ in range(n)]
        self.splitters_to_here: list[list[Position]] = [[] for _ in range(n)]

        # Symmetry
        self.symmetry_candidates: set[Symmetry] = {
            Symmetry.ROT,
            Symmetry.HOR,
            Symmetry.VER,
        }
        self.symmetry: Symmetry | None = None
        self.reflect_queue: deque[int] = deque()

        # Ephemeral (recomputed each turn)
        self.nearby_positions: list[Position] = []
        self.nearby_buildings: list[Position] = []
        self.healable_buildings: list[Position] = []
        self.adjacent_to_unconnected_harvester: set[Position] = set()
        self.adjacent_to_harvester: set[Position] = set()
        self.adjacent_to_enemy_launcher: set[Position] = set()
        # Tiles that are in the forward firing ray of an enemy gunner
        # or sentinel. Populated per-turn in state_update_map when a
        # visible enemy turret is encountered. Used as a soft cost
        # penalty in cost_grid so move_search routes bots around them.
        self.enemy_turret_ray_tiles: set[Position] = set()
        # Forward firing ray of FRIENDLY gunners/sentinels. Walking
        # into one blocks our own shot for that turn — same soft
        # penalty keeps bots off their own turrets' kill lanes.
        self.friendly_turret_ray_tiles: set[Position] = set()
        # Ore-denial tiles: for ores in our vision whose cardinal-8
        # halo contains an enemy bot or building, the ore's 4 cardinal
        # neighbours are candidate road-placement tiles. We pave them
        # with cheap roads (1 Ti base) to deny the enemy a harvester
        # feed position before they get one built.
        self.deny_ore_neighbours: set[Position] = set()
        self.nearest_enemy_turret: Position | None = None
        self.nearest_junction_site: Position | None = None

        # Role
        self.role: Role | None = None
        self.role_age: int = 0
        self.permanent_role: bool = False
        self.opportunistic: bool = self.rng.random() < 0.5

        # Economy
        self.ore_target: Position | None = None
        self.pending_bridge: Position | None = None
        self.dangling_output: Position | None = None
        self.branch_start: Position | None = None
        self.income_window: list[int] = [0] * 16
        self.spawned: int = 0

        # Repair
        self.repair_pos: Position | None = None
        self.repaired_prev: bool = True
        self.ally_sightings: dict = {}

        # Offense
        self.enemy_core_seen: bool = False
        self.offense_target: Position | None = None
        self.offense_turns: int = 0
        self.offense_launcher: Position | None = None
        # Track the tile we last fired at, plus the HP we expected to
        # see on the building there NEXT turn (i.e. pre-fire HP minus
        # our 2 dmg). If we revisit and the tile's current HP is
        # higher than that expectation, an enemy builder healed it —
        # concrete evidence we're being out-healed on this tile.
        self.last_fire_pos: Position | None = None
        self.last_fire_expected_hp: int = 0
        # Tiles we just got out-healed on: {tile: remaining_turns}.
        # Decremented at the top of run_attack; _pick_attack_destination
        # skips any entry still present. Stops the bounce loop where
        # we rotate around the same harvester's neighbours turn after
        # turn because the picker keeps picking one of a handful of
        # valid tiles and a nearby enemy builder just heals us off it.
        self.attack_tile_blacklist: dict[Position, int] = {}

        # Patrol
        self.patrol_head: Position | None = None
        self.patrol_trail: list[Position] = []

        # Scouting
        self.scout_active: bool = False
        self.scout_direction: int | None = None
        self.scout_target: Position | None = None
        self.scout_age: int = 0
        self.scout_radius: float = 10.0
        self.scout_initial_target: Position | None = None
        self.scout_initial_age: int = 0
        self.scout_initial_radius: float = 10.0

    def _init_pad_interior(self) -> None:
        """Seed interior cells of the padded cost grids. The border
        was already filled with INF by the constructor."""
        pad = self.pad
        pw = self.pw
        w = self.w
        h = self.h
        # cost_grid interior default: 1 (seen-empty equivalent, will
        # be overwritten when tiles come into vision).
        # conveyor_cost_grid interior default: 5 (unseen penalty so
        # A* doesn't plan long fog detours through unmapped terrain).
        cg = self.cost_grid
        ccg = self.conveyor_cost_grid
        for y in range(h):
            row_start = (y + pad) * pw + pad
            for x in range(w):
                cg[row_start + x] = 1
                ccg[row_start + x] = 5

    def _idx(self, pos: Position) -> int:
        return pos.y * self.w + pos.x

    def _pidx(self, pos: Position) -> int:
        """Padded flat index for cost_grid / conveyor_cost_grid."""
        return (pos.y + self.pad) * self.pw + (pos.x + self.pad)

    def in_bounds(self, pos: Position) -> bool:
        return 0 <= pos.x < self.w and 0 <= pos.y < self.h

    def get_env(self, pos: Position) -> Environment | None:
        if self.in_bounds(pos):
            return self.env[self._idx(pos)]
        return None

    def get_building(self, pos: Position) -> Building | None:
        if self.in_bounds(pos):
            return self.buildings[self._idx(pos)]
        return None

    def get_cost(self, pos: Position) -> int:
        if self.in_bounds(pos):
            return self.cost_grid[self._pidx(pos)]
        return INF

    def is_passable(self, pos: Position) -> bool | None:
        cost = self.get_cost(pos)
        if cost == INF:
            return False
        if cost < INF:
            return True
        return None

    def is_walkable(self, pos: Position) -> bool | None:
        if not self.is_passable(pos):
            return False
        match self.get_building(pos):
            case (
                BuildingConveyor()
                | BuildingRoad()
                | BuildingSplitter()
                | BuildingArmouredConveyor()
                | BuildingBridge()
            ):
                return True
            case _:
                return False

    def get_conveyors_to_here(self, pos: Position) -> list[Position]:
        if self.in_bounds(pos):
            return self.conveyors_to_here[self._idx(pos)]
        return []

    def is_buildable(self, pos: Position) -> bool:
        if self.in_bounds(pos):
            i = self._idx(pos)
            b = self.buildings[i]
            return self.env[i] != Environment.WALL and (
                b is None or b.team == self.my_team
            )
        return False

    def is_friendly_turret(self, pos: Position) -> bool:
        if not self.in_bounds(pos):
            return False
        b = self.buildings[self._idx(pos)]
        match b:
            case (
                None
                | BuildingConveyor()
                | BuildingRoad()
                | BuildingSplitter()
                | BuildingArmouredConveyor()
                | BuildingBridge()
            ):
                return False
            case _:
                return b.team == self.my_team
        return False

    def is_enemy_building(self, pos: Position) -> bool:
        if self.in_bounds(pos):
            b = self.buildings[self._idx(pos)]
            return b is not None and b.team != self.my_team
        return False

    def leads_to_enemy_building(self, pos: Position) -> bool:
        if self.in_bounds(pos):
            b = self.buildings[self._idx(pos)]
            if b is None or b.team != self.my_team:
                return False

            match b:
                case BuildingConveyor(direction=d):
                    output_location = pos.add(d)
                case BuildingBridge(target=t):
                    output_location = t
                case _:
                    return False
            return self.is_enemy_building(output_location)
        return False

    def update_line_load_counts(self, pos: Position | None) -> int:
        if pos is None:
            return 0
        if not self.in_bounds(pos):
            return 4
        i = self._idx(pos)
        if self.line_loads_computed[i]:
            return self.line_load_counts[i]
        b = self.buildings[i]
        next_pos = None
        match b:
            case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
                next_pos = pos.add(d)
            case BuildingBridge(target=t):
                next_pos = t
            case _:
                pass

        self.line_loads_computed[i] = True
        result = max(
            self.belt_load_counts[i],
            self.update_line_load_counts(next_pos),
        )
        self.line_load_counts[i] = result
        return result


