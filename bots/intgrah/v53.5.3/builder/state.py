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
from config import USE_HARDCODED_MAPS
from hardcode.map import CANDIDATES, SYMMETRY, TILES, decode
from util import INF, Symmetry

if TYPE_CHECKING:
    from hardcode.known import KnownMap

    from .role import Role

__all__ = ["State"]


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

        # Per-tile arrays (indexed by y * w + x)
        self.env: list[Environment | None] = [None] * n
        self.buildings: list[Building | None] = [None] * n
        self.hp: list[int] = [0] * n
        self.max_hp: list[int] = [0] * n
        self.cost_grid: list[int] = [2] * n
        self.conveyor_cost_grid: list[int] = [1] * n
        self.flow_history: list[int] = [0] * n
        self.nav_dist: list[int] = [-1] * n
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

        # Hardcoded map knowledge
        self.known_map: KnownMap | None = None
        if USE_HARDCODED_MAPS:
            self.known_map = _try_identify_map(self)
            if self.known_map is not None:
                self.symmetry = SYMMETRY[self.known_map]
                self.symmetry_candidates.clear()
                _load_map_tiles(self)

        # Ephemeral (recomputed each turn)
        self.nearby_positions: list[Position] = []
        self.nearby_buildings: list[Position] = []
        self.healable_buildings: list[Position] = []
        self.adjacent_to_unconnected_harvester: set[Position] = set()
        self.adjacent_to_unconnected_foundry: set[Position] = set()
        self.adjacent_to_harvester: set[Position] = set()
        self.adjacent_to_enemy_launcher: set[Position] = set()
        self.nearest_enemy_turret: Position | None = None
        self.nearest_junction_site: Position | None = None

        # Role
        self.role: Role | None = None
        self.role_age: int = 0
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

        # Patrol
        self.patrol_head: Position | None = None
        self.patrol_trail: list[Position] = []

        # Scouting
        self.scout_target: Position | None = None
        self.scout_age: int = 0
        self.scout_radius: float = 10.0

        # Frontier exploration
        self.frontier: set[int] = self._init_frontier()
        self.explore_target: int = -1

    def _idx(self, pos: Position) -> int:
        return pos.y * self.w + pos.x

    def in_bounds(self, pos: Position) -> bool:
        return 0 <= pos.x < self.w and 0 <= pos.y < self.h

    def _init_frontier(self) -> set[int]:
        w, h = self.w, self.h
        env = self.env
        deltas = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
        frontier: set[int] = set()
        for i in range(w * h):
            if env[i] is not None:
                continue
            cx, cy = i % w, i // w
            for dx, dy in deltas:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h and env[ny * w + nx] is not None:
                    frontier.add(i)
                    break
        return frontier

    def update_frontier_at(self, i: int) -> None:
        w, h = self.w, self.h
        env = self.env
        deltas = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
        self.frontier.discard(i)
        cx, cy = i % w, i // w
        for dx, dy in deltas:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                ni = ny * w + nx
                if env[ni] is None:
                    self.frontier.add(ni)
                else:
                    self.frontier.discard(ni)

    def get_env(self, pos: Position) -> Environment | None:
        if self.in_bounds(pos):
            return self.env[self._idx(pos)]
        return None

    def get_building(self, pos: Position) -> Building | None:
        if self.in_bounds(pos):
            return self.buildings[self._idx(pos)]
        return None

    def get_cost(self, pos: Position) -> float:
        if self.in_bounds(pos):
            return self.cost_grid[self._idx(pos)]
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


def _try_identify_map(state: State) -> KnownMap | None:
    key = (state.w, state.h, state.my_core)
    candidates = CANDIDATES.get(key)
    if candidates is None or len(candidates) != 1:
        return None
    return candidates[0]


def _load_map_tiles(state: State) -> None:
    km = state.known_map
    assert km is not None
    n = state.w * state.h
    tiles = decode(TILES[km](), n)
    for i in range(n):
        state.env[i] = tiles[i]
