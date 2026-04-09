from __future__ import annotations

import heapq
import math
import random
from collections import deque
from typing import TYPE_CHECKING, Final, override

from building import (
    ETYPE_BUILDING,
    Building,
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingCore,
    BuildingGunner,
    BuildingHarvester,
    BuildingLauncher,
    BuildingRoad,
    BuildingSentinel,
    BuildingSplitter,
)
from cambc import (
    Controller,
    Direction,
    EntityType,
    Environment,
    GameConstants,
    Position,
    Team,
)
from config import DEBUG_DUMP, USE_HARDCODED_MAPS
from hardcode.map import CANDIDATES, SYMMETRY, TILES, decode
from unit import Unit
from util import DIR4, DIR8, DIR8_DELTA, INF, Symmetry
from util_extra import (
    can_afford,
    chebyshev,
    closest,
    get_direction_object,
    reachable_path_end,
    try_move,
)
from visualiser import Grid, Palette, Scalar, Tiles, VectorField, emit

from .role import (
    ROLE_OPENING,
    ROLE_REASSIGN_AFTER,
    ROLE_REASSIGN_PERIOD,
    ROLE_TRANSITION,
    ROLE_WEIGHTS,
    Role,
)

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["Builder"]

WALKABLE_ENTITIES = [
    EntityType.CONVEYOR,
    EntityType.ROAD,
    EntityType.SPLITTER,
    EntityType.ARMOURED_CONVEYOR,
    EntityType.BRIDGE,
]


# ================================================================================
#  Conveyor A* (weighted pathfinding for conveyor routing only)
# ================================================================================

_CONV_INF = float("inf")
_CONV_CPU_BUDGET = 1729
_CONV_TARGET_DRIFT_SQ = 25
_CONV_TIEBREAK_EPS = 1e-5
DIAG_WEIGHT = 4

_CONV_NEIGHBORS = [
    (1, 0, 0),
    (-1, 0, 0),
    (0, 1, 0),
    (0, -1, 0),
    (1, 1, DIAG_WEIGHT),
    (1, -1, DIAG_WEIGHT),
    (-1, 1, DIAG_WEIGHT),
    (-1, -1, DIAG_WEIGHT),
]
random.shuffle(_CONV_NEIGHBORS)


class ConvAstar:
    def __init__(self) -> None:
        self._w = 0
        self._h = 0
        self._dist: list[float] = []
        self._visited = bytearray()
        self._prev_visited = bytearray()
        self._q: list[tuple[float, Position]] = []
        self._finished = True
        self._no_path = False
        self._prev_no_path = False
        self._running_target: Position | None = None
        self._prev_target: Position | None = None

    def _reset(self, w: int, h: int) -> None:
        if self._w != w or self._h != h:
            self._w, self._h = w, h
            self._dist = [_CONV_INF] * (w * h)
        self._no_path = False
        self._visited = bytearray((self._w * self._h + 7) // 8)
        self._q = []

    def _run(
        self,
        cost: list[float],
        ct: Controller,
        start: Position,
        goal: Position,
    ) -> bool:
        w = self._w
        dist = self._dist
        visited = self._visited
        q = self._q

        idx = goal.y * w + goal.x
        dist[idx] = 0
        visited[idx >> 3] |= 1 << (idx & 0b111)
        heapq.heappush(q, (0.0, goal))

        while q:
            _, current = heapq.heappop(q)
            if current == start:
                return True
            if ct.get_cpu_time_elapsed() > _CONV_CPU_BUDGET:
                return False

            cur_dist = dist[current.y * w + current.x]
            for dx, dy, extra in _CONV_NEIGHBORS:
                nx, ny = current.x + dx, current.y + dy
                if not (0 <= nx < self._w and 0 <= ny < self._h):
                    continue
                idx = ny * w + nx
                seen = visited[idx >> 3] & (1 << (idx & 0b111))
                if not seen:
                    dist[idx] = _CONV_INF
                visited[idx >> 3] |= 1 << (idx & 0b111)
                move_cost = cost[idx]
                if move_cost == _CONV_INF:
                    continue
                new_dist = cur_dist + move_cost + extra
                if new_dist >= dist[idx]:
                    continue
                dist[idx] = new_dist
                nb = Position(nx, ny)
                h = (abs(nb.x - start.x) + abs(nb.y - start.y)) + _CONV_TIEBREAK_EPS * (
                    abs(nb.x - start.x) + abs(nb.y - start.y)
                )
                heapq.heappush(q, (new_dist + h, nb))

        self._no_path = True
        return True

    def _extract_path(
        self,
        cost: list[float],
        start: Position,
        target: Position,
    ) -> list[Position]:
        w = self._w
        path: list[Position] = []
        current = start
        while current != target:
            if current in path:
                break
            path.append(current)
            best_dist = _CONV_INF
            best = current
            for dx, dy, extra in _CONV_NEIGHBORS:
                nx, ny = current.x + dx, current.y + dy
                idx = ny * w + nx
                if (
                    0 <= nx < self._w
                    and 0 <= ny < self._h
                    and (self._prev_visited[idx // 8] & (1 << (idx % 8)))
                    and cost[idx] != _CONV_INF
                ):
                    d = self._dist[idx] + extra
                    if d < best_dist:
                        best_dist = d
                        best = Position(nx, ny)
            current = best
        path.append(target)
        return path

    def search(
        self,
        state: Builder,
        ct: Controller,
        start: Position,
        target: Position,
    ) -> list[Position] | None:
        cost = state.conveyor_cost_grid
        if (
            self._finished
            or self._running_target is None
            or target.distance_squared(self._running_target) > _CONV_TARGET_DRIFT_SQ
        ):
            self._reset(state.w, state.h)
        else:
            target = self._running_target

        self._running_target = target
        self._finished = self._run(cost, ct, start, target)

        if self._finished:
            self._prev_visited = self._visited
            self._prev_target = target
            self._prev_no_path = self._no_path

        if self._prev_target is None:
            return None
        diff = target.distance_squared(self._prev_target)
        if diff <= _CONV_TARGET_DRIFT_SQ and diff < start.distance_squared(target):
            if self._no_path:
                return None
            return self._extract_path(cost, start, target)
        return None

    def search_blocked(
        self,
        state: Builder,
        ct: Controller,
        start: Position,
        goal: Position,
    ) -> list[Position] | None:
        cost = state.conveyor_cost_grid
        saved: list[tuple[int, float]] = []
        for pos in ct.get_nearby_tiles(2):
            if ct.get_tile_builder_bot_id(pos) is not None and pos != start:
                idx = pos.y * state.w + pos.x
                saved.append((idx, cost[idx]))
                cost[idx] = _CONV_INF
        result = self.search(state, ct, start, goal)
        for idx, val in saved:
            cost[idx] = val
        return result

    @property
    def no_path(self) -> bool:
        return self._prev_no_path


conv_search = ConvAstar()


# ================================================================================
#  Visualiser Dump
# ================================================================================

_TRANSPARENT = (0, 0, 0, 0)

_P_FOG = Palette(
    stops=[(0.0, 0, 0, 0, 0), (1.0, 0, 0, 0, 180)],
    special={0: _TRANSPARENT},
)
_P_COST = Palette(
    stops=[(0.0, 50, 200, 50, 140), (1.0, 200, 50, 50, 140)],
    special={-1: _TRANSPARENT},
)
_P_DIST = Palette(
    stops=[(0.0, 50, 200, 50, 140), (1.0, 200, 50, 50, 140)],
    special={-1: _TRANSPARENT},
)


def _parent_to_angles(parent: list[int], w: int) -> list[float | None]:
    result: list[float | None] = []
    for i, p in enumerate(parent):
        if p < 0 or p == i:
            result.append(None)
        else:
            dx = p % w - i % w
            dy = p // w - i // w
            result.append(math.atan2(dy, dx))
    return result


ROAD_COST = 3


# ================================================================================
#  Builder
# ================================================================================


class Builder(Unit):
    # ================================================================================
    #  Initialization
    # ================================================================================

    @staticmethod
    def _find_core(ct: Controller) -> Position:
        my_team = ct.get_team()
        for bid in ct.get_nearby_buildings():
            if (
                ct.get_team(bid) == my_team
                and ct.get_entity_type(bid) == EntityType.CORE
            ):
                return ct.get_position(bid)
        msg = "Core not visible at spawn"
        raise AssertionError(msg)

    @staticmethod
    def init_pnb(w: int, h: int) -> list[list[int]]:
        n = w * h
        pnb: list[list[int]] = [[] for _ in range(n)]
        for i in range(n):
            cx, cy = i % w, i // w
            for dx, dy in DIR8_DELTA:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h:
                    pnb[i].append(ny * w + nx)
        return pnb

    @staticmethod
    def update_pnb(
        w: int,
        h: int,
        cost: list[int],
        pnb: list[list[int]],
        i: int,
    ) -> None:
        cx, cy = i % w, i // w
        passable = cost[i] < INF
        pnb[i] = []
        if passable:
            for dx, dy in DIR8_DELTA:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h:
                    ni = ny * w + nx
                    if cost[ni] < INF:
                        pnb[i].append(ni)
        for dx, dy in DIR8_DELTA:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                ni = ny * w + nx
                if cost[ni] >= INF:
                    continue
                nb_list = pnb[ni]
                if passable:
                    if i not in nb_list:
                        nb_list.append(i)
                elif i in nb_list:
                    nb_list.remove(i)

    @override
    def __init__(self, ct: Controller) -> None:
        super().__init__(ct)
        self.my_core: Final[Position] = Builder._find_core(ct)
        self.opportunistic: Final[bool] = self.rng.random() < 0.5
        self.en_team: Final[Team] = Team.B if self.my_team == Team.A else Team.A

        w, h = self.w, self.h
        n = w * h

        self.env: list[Environment | None] = [None] * n
        self.buildings: list[Building | None] = [None] * n
        self.hp: list[int] = [0] * n
        self.max_hp: list[int] = [0] * n
        self.cost_grid: list[int] = [1] * n
        self.conveyor_cost_grid = [1.0] * n
        self.belt_load_counts = [0] * n
        self.line_load_counts = [0] * n
        self.line_loads_computed = [False] * n
        self.network_in_edges: list[list[Position]] = [[] for _ in range(n)]

        self.symmetry_candidates: set[Symmetry] = set(Symmetry)
        self.symmetry: Symmetry | None = None
        self.reflect_queue: deque[int] = deque()

        if USE_HARDCODED_MAPS:
            known_map = CANDIDATES.get((w, h, self.my_core))
            if known_map is not None:
                self.symmetry = SYMMETRY[known_map]
                self.symmetry_candidates = {self.symmetry}
                self.env = decode(TILES[known_map](), n)

        self.nearby_buildings: list[Position] = []
        self.healable_buildings: list[Position] = []
        self.adjacent_to_unconnected_harvester: set[Position] = set()
        self.adjacent_to_harvester: set[Position] = set()
        self.adjacent_to_enemy_launcher: set[Position] = set()
        self.nearest_enemy_turret: Position | None = None
        self.nearest_junction_site: Position | None = None

        self.role: Role | None = None
        self.role_age: int = 0
        self.permanent_role: bool = False

        self.ore_target: Position | None = None
        self.pending_bridge: Position | None = None
        self.dangling_output: Position | None = None
        self.branch_start: Position | None = None

        self.repair_pos: Position | None = None
        self.repaired_prev: bool = True
        self.ally_sightings: dict = {}

        self.enemy_core_seen: bool = False
        self.offense_target: Position | None = None
        self.offense_turns: int = 0
        self.offense_launcher: Position | None = None

        self.patrol_head: Position | None = None
        self.patrol_trail: list[Position] = []

        self.scout_target: Position | None = None
        self.scout_age: int = 0
        self.scout_radius: float = 10.0

        self.pnb: list[list[int]] = Builder.init_pnb(w, h)
        self.nav_parent: list[int] = [-1] * n
        self.nav_dist: list[int] = [-1] * n

    # ================================================================================
    #  Map State Queries
    # ================================================================================

    def get_env(self, pos: Position) -> Environment | None:
        return self.env[self.idx(pos)]

    def get_building(self, pos: Position) -> Building | None:
        return self.buildings[self.idx(pos)]

    def get_cost(self, pos: Position) -> float:
        return self.cost_grid[self.idx(pos)]

    def is_passable(self, pos: Position) -> bool:
        return self.get_cost(pos) < INF

    def is_walkable(self, pos: Position) -> bool:
        if not self.is_passable(pos):
            return False
        match self.get_building(pos):
            case (
                BuildingArmouredConveyor()
                | BuildingConveyor()
                | BuildingBridge()
                | BuildingRoad()
                | BuildingSplitter()
            ):
                return True
            case _:
                return False

    def get_conveyors_to_here(self, pos: Position) -> list[Position]:
        return self.network_in_edges[self.idx(pos)]

    def is_buildable(self, pos: Position) -> bool:
        if self.in_bounds(pos):
            i = self.idx(pos)
            b = self.buildings[i]
            return self.env[i] != Environment.WALL and (
                b is None or b.team == self.my_team
            )
        return False

    def is_friendly_turret(self, pos: Position) -> bool:
        if not self.in_bounds(pos):
            return False
        b = self.buildings[self.idx(pos)]
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

    def is_enemy_building(self, pos: Position) -> bool:
        if self.in_bounds(pos):
            b = self.buildings[self.idx(pos)]
            return b is not None and b.team != self.my_team
        return False

    def leads_to_enemy_building(self, pos: Position) -> bool:
        if self.in_bounds(pos):
            match self.buildings[self.idx(pos)]:
                case BuildingConveyor(team=self.en_team, direction=d):
                    return self.is_enemy_building(pos.add(d))
                case BuildingBridge(team=self.en_team, target=t):
                    return self.is_enemy_building(t)
                case _:
                    return False
        return False

    def update_line_load_counts(self, pos: Position | None) -> int:
        if pos is None:
            return 0
        if not self.in_bounds(pos):
            return 4
        i = self.idx(pos)
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
        result = max(self.belt_load_counts[i], self.update_line_load_counts(next_pos))
        self.line_load_counts[i] = result
        return result

    # ================================================================================
    #  Map Update
    # ================================================================================

    @staticmethod
    def _make_building(ct: Controller, bid: int, etype: EntityType) -> Building | None:
        team = ct.get_team(bid)
        match etype:
            case (
                EntityType.CONVEYOR
                | EntityType.ARMOURED_CONVEYOR
                | EntityType.SPLITTER
                | EntityType.GUNNER
                | EntityType.SENTINEL
                | EntityType.BREACH
            ):
                cls = ETYPE_BUILDING[etype]
                return cls(team, ct.get_direction(bid))
            case EntityType.BRIDGE:
                return BuildingBridge(team, ct.get_bridge_target(bid))
            case _:
                cls = ETYPE_BUILDING.get(etype)
                if cls is None:
                    return None
                return cls(team)

    @staticmethod
    def _load_penalty(load: int) -> float:
        match load:
            case 0:
                return 0
            case 1:
                return 0.5
            case 2:
                return 3.0
            case 3:
                return 10.0
            case _:
                return 500.0

    def _can_place_junction(self, ct: Controller, pos: Position) -> bool:
        match self.get_building(pos):
            case None:
                pass
            case BuildingConveyor(team=t) | BuildingRoad(team=t) if t == ct.get_team():
                pass
            case _:
                return False

        conveyors = self.get_conveyors_to_here(pos)
        adjacent_conveyors = [c for c in conveyors if c.distance_squared(pos) <= 2]
        if len(adjacent_conveyors) > 1 or len(conveyors) == 0:
            return False
        buildable_count = 0
        for d in DIR4:
            new_pos = pos.add(d)
            if self.get_env(new_pos) != Environment.EMPTY:
                continue
            match self.get_building(new_pos):
                case None:
                    buildable_count += 1
                case BuildingConveyor() | BuildingBridge() | BuildingSplitter():
                    pass
                case b if b.team == ct.get_team():
                    buildable_count += 1

        return buildable_count >= 1

    def _update_map(self, ct: Controller) -> None:
        w = self.w
        nearby_tiles = ct.get_nearby_tiles()

        self.healable_buildings = [
            p for p in self.healable_buildings if not ct.is_in_vision(p)
        ]
        self.adjacent_to_enemy_launcher = {
            p for p in self.adjacent_to_enemy_launcher if not ct.is_in_vision(p)
        }

        for pos in nearby_tiles:
            if 0 <= pos.x < self.w and 0 <= pos.y < self.h:
                i = pos.y * w + pos.x
                self.network_in_edges[i] = [
                    p for p in self.network_in_edges[i] if not ct.is_in_vision(p)
                ]

        for pos in nearby_tiles:
            if 0 <= pos.x < self.w and 0 <= pos.y < self.h:
                i = pos.y * w + pos.x
                self.env[i] = ct.get_tile_env(pos)
                building_id = ct.get_tile_building_id(pos)
                if (
                    building_id is not None
                    and ct.get_entity_type(building_id) != EntityType.MARKER
                ):
                    etype = ct.get_entity_type(building_id)
                    bld = Builder._make_building(ct, building_id, etype)
                    self.buildings[i] = bld
                    self.hp[i] = ct.get_hp(building_id)
                    self.max_hp[i] = ct.get_max_hp(building_id)

                    match bld:
                        case BuildingConveyor() | BuildingBridge():
                            if ct.get_stored_resource(building_id) is not None:
                                self.belt_load_counts[i] += 1
                            else:
                                self.belt_load_counts[i] = 0
                        case BuildingSplitter():
                            self.belt_load_counts[i] = 100

                    match bld:
                        case BuildingConveyor(direction=d):
                            target_pos = pos.add(d)
                            if (
                                0 <= target_pos.x < self.w
                                and 0 <= target_pos.y < self.h
                            ):
                                ti = target_pos.y * w + target_pos.x
                                self.network_in_edges[ti].append(pos)
                        case BuildingBridge(target=t):
                            if 0 <= t.x < self.w and 0 <= t.y < self.h:
                                ti = t.y * w + t.x
                                self.network_in_edges[ti].append(pos)
                        case BuildingSplitter(direction=d):
                            for sd in [
                                d,
                                d.rotate_right().rotate_right(),
                                d.rotate_left().rotate_left(),
                            ]:
                                target_pos = pos.add(sd)
                                if (
                                    0 <= target_pos.x < self.w
                                    and 0 <= target_pos.y < self.h
                                ):
                                    ti = target_pos.y * w + target_pos.x

                    self.nearby_buildings.append(pos)
                    if (
                        self.hp[i] < self.max_hp[i]
                        and bld is not None
                        and bld.team == ct.get_team()
                    ):
                        self.healable_buildings.append(pos)
                    match bld:
                        case BuildingLauncher(team=t) if t != ct.get_team():
                            for d in DIR8:
                                self.adjacent_to_enemy_launcher.add(pos.add(d))
                else:
                    self.buildings[i] = None

                terrain = self.env[i]
                bld = self.buildings[i]
                if terrain == Environment.WALL:
                    cost = INF
                    conveyor_cost = float("inf")
                elif bld is not None:
                    match bld:
                        case (
                            BuildingConveyor()
                            | BuildingRoad()
                            | BuildingSplitter()
                            | BuildingArmouredConveyor()
                            | BuildingBridge()
                        ):
                            cost = 1
                            conveyor_cost = 1
                        case BuildingCore(team=t) if t == ct.get_team():
                            cost = 1
                            conveyor_cost = 1
                        case _:
                            cost = INF
                            conveyor_cost = float("inf")
                elif terrain in (
                    Environment.EMPTY,
                    Environment.ORE_TITANIUM,
                    Environment.ORE_AXIONITE,
                ):
                    cost = ROAD_COST
                    conveyor_cost = 1 if terrain == Environment.EMPTY else 50.0
                else:
                    cost = 1
                    conveyor_cost = 1
                old_cost = self.cost_grid[i]
                self.cost_grid[i] = cost
                self.line_loads_computed[i] = False
                self.conveyor_cost_grid[i] = conveyor_cost
                old_pass = old_cost < INF
                new_pass = cost < INF
                if old_pass != new_pass:
                    Builder.update_pnb(self.w, self.h, self.cost_grid, self.pnb, i)

        my_pos = ct.get_position()
        for pos in nearby_tiles:
            if (
                self.env[pos.y * w + pos.x]
                in [Environment.ORE_TITANIUM, Environment.ORE_AXIONITE]
                and self.buildings[pos.y * w + pos.x] is None
            ):
                pass

        if self.nearest_enemy_turret:
            match self.buildings[pos.y * w + pos.x]:
                case BuildingGunner(team=t) | BuildingSentinel(team=t) if (
                    t != ct.get_team()
                ):
                    pass
                case _:
                    self.nearest_enemy_turret = None
        min_dist = float("inf")
        for pos in nearby_tiles:
            match self.buildings[pos.y * w + pos.x]:
                case BuildingGunner(team=t) | BuildingSentinel(team=t) if (
                    t != ct.get_team()
                ):
                    dist = (pos.x - my_pos.x) ** 2 + (pos.y - my_pos.y) ** 2
                    if dist < min_dist:
                        min_dist = dist
                        self.nearest_enemy_turret = pos

    def _update_splittable_locations(self, ct: Controller) -> None:
        w = self.w
        self.adjacent_to_unconnected_harvester = {
            p for p in self.adjacent_to_unconnected_harvester if not ct.is_in_vision(p)
        }
        self.adjacent_to_harvester = {
            p for p in self.adjacent_to_harvester if not ct.is_in_vision(p)
        }
        for pos in ct.get_nearby_tiles():
            i = pos.y * w + pos.x
            bld = self.get_building(pos)
            match bld:
                case BuildingHarvester():
                    adjacent_conveyor = False
                    for d in DIR4:
                        match self.get_building(pos.add(d)):
                            case (
                                BuildingConveyor(team=t)
                                | BuildingBridge(team=t)
                                | BuildingSplitter(team=t)
                                | BuildingArmouredConveyor(team=t)
                            ) if t == ct.get_team():
                                adjacent_conveyor = True
                                break
                    if not adjacent_conveyor:
                        for d in DIR4:
                            self.adjacent_to_unconnected_harvester.add(pos.add(d))
                    for d in DIR4:
                        self.adjacent_to_harvester.add(pos.add(d))
            if pos in self.adjacent_to_enemy_launcher:
                self.cost_grid[i] += 20

            match bld:
                case (
                    BuildingConveyor(team=t)
                    | BuildingArmouredConveyor(team=t)
                    | BuildingSplitter(team=t)
                    | BuildingBridge(team=t)
                ) if t == ct.get_team():
                    self.conveyor_cost_grid[i] += Builder._load_penalty(
                        self.update_line_load_counts(pos),
                    )

        my_position = ct.get_position()
        if self.nearest_junction_site and not self._can_place_junction(
            ct,
            self.nearest_junction_site,
        ):
            self.nearest_junction_site = None
        for pos in ct.get_nearby_tiles():
            if (
                self.nearest_junction_site is None
                or (
                    self.nearest_junction_site.distance_squared(my_position)
                    < pos.distance_squared(my_position)
                )
            ) and self._can_place_junction(ct, pos):
                self.nearest_junction_site = pos

    # ================================================================================
    #  Symmetry
    # ================================================================================

    def _mirror(self, pos: Position) -> Position:
        match self.symmetry:
            case Symmetry.ROT:
                return Position(self.w - 1 - pos.x, self.h - 1 - pos.y)
            case Symmetry.HOR:
                return Position(pos.x, self.h - 1 - pos.y)
            case Symmetry.VER:
                return Position(self.w - 1 - pos.x, pos.y)
            case None:
                return pos

    def _set_enemy_core(self) -> None:
        core = self._mirror(self.my_core)
        w = self.w
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                cx, cy = core.x + dx, core.y + dy
                self.cost_grid[cy * w + cx] = INF

    def _apply_symmetry(self, new_tiles: list[tuple[Position, Environment]]) -> None:
        had_symmetry = self.symmetry is not None
        if self.symmetry is None:
            self._eliminate_symmetries(new_tiles)
        if self.symmetry is None:
            return
        w = self.w
        if had_symmetry:
            source = new_tiles
        else:
            self._set_enemy_core()
            source = [
                (Position(i % w, i // w), e)
                for i, e in enumerate(self.env)
                if e is not None
            ]
        for t, env in source:
            m = self._mirror(t)
            mi = m.y * w + m.x
            if self.env[mi] is not None:
                continue
            self.env[mi] = env
            self.reflect_queue.append(mi)

    def _drain_reflect_queue(self) -> None:
        pending = self.reflect_queue
        if not pending:
            return
        _reflect_budget = 25
        n = min(len(pending), _reflect_budget)
        for _ in range(n):
            i = pending.popleft()
            terrain = self.env[i]
            if terrain == Environment.WALL:
                self.cost_grid[i] = INF
                self.conveyor_cost_grid[i] = float("inf")
            elif terrain in (
                Environment.EMPTY,
                Environment.ORE_TITANIUM,
                Environment.ORE_AXIONITE,
            ):
                self.cost_grid[i] = ROAD_COST
                self.conveyor_cost_grid[i] = 1 if terrain == Environment.EMPTY else 50.0

    def _eliminate_symmetries(
        self,
        new_tiles: list[tuple[Position, Environment]],
    ) -> None:
        if not self.symmetry_candidates:
            return

        w, h = self.w, self.h
        invalid: set[Symmetry] = set()

        for sym in self.symmetry_candidates:
            for pos, env in new_tiles:
                match sym:
                    case Symmetry.HOR:
                        sx, sy = pos.x, h - 1 - pos.y
                    case Symmetry.VER:
                        sx, sy = w - 1 - pos.x, pos.y
                    case Symmetry.ROT:
                        sx, sy = w - 1 - pos.x, h - 1 - pos.y

                mirror_env = self.env[sy * w + sx]
                if mirror_env is not None and mirror_env != env:
                    invalid.add(sym)
                    break

                b1 = self.buildings[pos.y * w + pos.x]
                b2 = self.buildings[sy * w + sx]
                match b1:
                    case BuildingCore():
                        is_core1 = True
                    case _:
                        is_core1 = False
                match b2:
                    case BuildingCore():
                        is_core2 = True
                    case _:
                        is_core2 = False
                if is_core1 != is_core2:
                    invalid.add(sym)
                    break

        self.symmetry_candidates -= invalid

        if self.symmetry is None and len(self.symmetry_candidates) == 1:
            self.symmetry = next(iter(self.symmetry_candidates))

    # ================================================================================
    #  Role Update
    # ================================================================================

    def _pick_initial_role(self, ct: Controller) -> Role:
        if ct.get_current_round() > 10:
            early = ct.get_current_round() < 200
            w = ROLE_WEIGHTS[early]
            roles, weights = zip(*w.items(), strict=False)
            return self.rng.choices(roles, weights=weights)[0]
        idx = ct.get_unit_count() - 3
        if idx < len(ROLE_OPENING):
            role, perm = ROLE_OPENING[idx]
            self.permanent_role = perm
            return role
        return Role.ECON

    def _update_role(self, ct: Controller) -> None:
        if self.role is None:
            self.role = self._pick_initial_role(ct)

        if (
            self.role_age > ROLE_REASSIGN_PERIOD
            and ct.get_current_round() > ROLE_REASSIGN_AFTER
            and not self.permanent_role
        ):
            self.role_age = 0
            row = ROLE_TRANSITION[self.role]
            roles = list(row)
            weights = [row[role] for role in roles]
            self.role = self.rng.choices(roles, weights=weights)[0]
            if self.role == Role.OFFENSE:
                self.role_age = -300

        self.role_age += 1

    # ================================================================================
    #  Economy Update
    # ================================================================================

    def _is_dangling(self, ct: Controller, pos: Position) -> bool:
        if not self.in_bounds(pos):
            return False

        i = pos.y * self.w + pos.x
        b = self.buildings[i]
        if b is None:
            if self.env[i] == Environment.WALL:
                return False

        elif not isinstance(b, BuildingRoad) or b.team != ct.get_team():
            return False

        if self.network_in_edges[i]:
            return True

        return pos in self.adjacent_to_unconnected_harvester

    def _is_valid_loose_end_target(self, ct: Controller, pos: Position) -> bool:
        if not self._is_dangling(ct, pos):
            return False

        my_id = ct.get_id()
        if ct.is_in_vision(pos):
            bid = ct.get_tile_builder_bot_id(pos)
            friendly = ct.get_team(bid) == ct.get_team()
            if bid is not None and bid != my_id and friendly:
                return False

        leading = self.get_conveyors_to_here(pos)
        for lpos in leading:
            if not ct.is_in_vision(lpos):
                continue
            lbid = ct.get_tile_builder_bot_id(lpos)
            friendly = ct.get_team(lbid) == ct.get_team()
            if lbid is not None and lbid != my_id and friendly:
                return False
        return True

    def _find_dangling(self, ct: Controller) -> Position | None:
        vision_radius = ct.get_vision_radius_sq()
        nearby = ct.get_nearby_tiles(vision_radius)

        candidates = [pos for pos in nearby if self._is_valid_loose_end_target(ct, pos)]

        if not candidates:
            return None

        my_pos = ct.get_position()
        return closest(my_pos, candidates)

    def _update_dangling(self, ct: Controller) -> None:
        my_pos = ct.get_position()
        if self._is_dangling(ct, my_pos):
            self.dangling_output = my_pos
        else:
            match self.get_building(my_pos):
                case (
                    BuildingConveyor(direction=d)
                    | BuildingArmouredConveyor(direction=d)
                ):
                    target = my_pos.add(d)
                    if self._is_dangling(ct, target):
                        self.dangling_output = target
                case _:
                    for d in DIR8:
                        n = my_pos.add(d)
                        if self._is_dangling(ct, n):
                            self.dangling_output = n
                            break
        if self.pending_bridge:
            self.dangling_output = self.pending_bridge
        elif self.dangling_output is None or not self._is_dangling(
            ct,
            self.dangling_output,
        ):
            self.dangling_output = self._find_dangling(ct)

    def _update_ore_target(self, ct: Controller) -> None:
        my_pos = ct.get_position()
        candidate_ore = self._pick_ore_target(ct)
        if (
            not self.ore_target
            or not self._ore_available(ct, self.ore_target)
            or (
                candidate_ore
                and candidate_ore.distance_squared(my_pos) <= 2
                and self.ore_target.distance_squared(my_pos) > 2
            )
        ):
            self.ore_target = candidate_ore

    def _update_economy(self, ct: Controller) -> None:
        t0 = ct.get_cpu_time_elapsed()
        self._update_dangling(ct)
        t1 = ct.get_cpu_time_elapsed()
        print(f"  loose={t1 - t0}us")
        self._update_ore_target(ct)
        t2 = ct.get_cpu_time_elapsed()
        print(f"  ore={t2 - t1}us")

    # ================================================================================
    #  BFS Update
    # ================================================================================

    def _update_bfs(self, ct: Controller) -> None:
        w = self.w
        n = w * self.h
        pos = ct.get_position()
        si = pos.y * w + pos.x
        pnb = self.pnb
        parent = self.nav_parent
        dist = self.nav_dist

        for i in range(n):
            parent[i] = -1
            dist[i] = -1

        parent[si] = si
        dist[si] = 0

        q: deque[int] = deque([si])
        while q:
            node = q.popleft()
            d = dist[node] + 1
            for ni in pnb[node]:
                if parent[ni] != -1:
                    continue
                parent[ni] = node
                dist[ni] = d
                q.append(ni)

    def _extract_path(self, gx: int, gy: int) -> list[int] | None:
        w = self.w
        gi = gy * w + gx
        parent = self.nav_parent
        if parent[gi] == -1:
            return None
        path: list[int] = []
        cur = gi
        while parent[cur] != cur:
            path.append(cur)
            cur = parent[cur]
        path.append(cur)
        path.reverse()
        return path

    # ================================================================================
    #  Helpers: Movement & Building
    # ================================================================================

    def _make_move(self, ct: Controller, target: Position) -> bool:
        if ct.get_position() == target:
            return True

        path = self._extract_path(target.x, target.y)
        if path and len(path) >= 2:
            w = self.w
            nx, ny = path[1] % w, path[1] // w
            self._try_move_with_build(ct, Position(nx, ny))
            return True
        return False

    def _try_move_with_road(self, ct: Controller, target_pos: Position) -> bool:
        if self.get_cost(target_pos) > 1 and ct.can_build_road(target_pos):
            ct.build_road(target_pos)
        return try_move(ct, target_pos)

    def _try_move_with_build(self, ct: Controller, target_pos: Position) -> bool:
        return self._try_move_with_road(ct, target_pos)

    @staticmethod
    def _try_attack(ct: Controller) -> bool:
        position = ct.get_position()
        if ct.can_fire(position):
            ct.fire(position)
            return True
        return False

    @staticmethod
    def _try_place(
        ct: Controller,
        etype: EntityType,
        pos: Position,
        extra: Direction | Position | None = None,
        *,
        destroy: bool = True,
    ) -> bool:
        if not can_afford(ct, etype):
            return False
        if destroy and ct.can_destroy(pos):
            ct.destroy(pos)
        if ct.can_build(etype, pos, extra):
            ct.build(etype, pos, extra)
            return True
        return False

    def _trace_downstream(
        self,
        start_pos: Position,
        target_head: Position | None,
        path: list[Position] | None = None,
    ) -> list[Position]:
        if path is None:
            path = []
        current_pos = start_pos
        while True:
            path.append(current_pos)
            bld = self.get_building(current_pos)
            match bld:
                case (
                    BuildingConveyor(direction=d)
                    | BuildingArmouredConveyor(direction=d)
                ):
                    current_pos = current_pos.add(d)
                case BuildingSplitter(direction=d):
                    for sd in DIR4:
                        if sd == d.opposite():
                            continue
                        new_pos = current_pos.add(sd)
                        if target_head:
                            new_path = self._trace_downstream(
                                new_pos,
                                target_head,
                                path=path[:],
                            )
                            if new_path and target_head in new_path:
                                return new_path
                        elif self.get_building(new_pos) is None:
                            path.append(new_pos)
                            return path
                    current_pos = current_pos.add(d)
                case BuildingBridge(target=t):
                    current_pos = t
                case _:
                    break
            if current_pos in path:
                break
        return path

    def _try_heal(
        self,
        ct: Controller,
        position: Position,
        *,
        conserve_ti: bool = True,
    ) -> bool:
        if conserve_ti and self.repair_pos is not None:
            i = self.idx(self.repair_pos)
            if not self.buildings[i] or self.hp[i] > self.max_hp[i] - 4:
                return False
        if ct.can_heal(position):
            ct.heal(position)
            return True
        return False

    def _get_enemy_core_pos(self) -> Position:
        w, h = self.w, self.h
        cp = self.my_core
        candidates = self.symmetry_candidates

        if Symmetry.ROT in candidates:
            return Position(w - 1 - cp.x, h - 1 - cp.y)
        if Symmetry.VER in candidates:
            return Position(w - 1 - cp.x, cp.y)
        if Symmetry.HOR in candidates:
            return Position(cp.x, h - 1 - cp.y)

        return Position(w - 1 - cp.x, h - 1 - cp.y)

    def _move_random(self, ct: Controller) -> bool:
        dir8 = DIR8[:]
        self.rng.shuffle(dir8)
        for direction in dir8:
            if ct.can_move(direction):
                ct.move(direction)
                return True
        return False

    def _trace_upstream(self, position: Position) -> list[Position]:
        path: list[Position] = []
        conveyors = [position]
        while len(conveyors) > 0:
            position = conveyors[0]
            conveyors = self.get_conveyors_to_here(position)
            if position in path:
                break
            path.append(position)
        return path

    def _is_enemy_building_at(self, ct: Controller, pos: Position) -> bool:
        b = self.get_building(pos)
        return b is not None and b.team != ct.get_team()

    # ================================================================================
    #  Visualiser Dump
    # ================================================================================

    def _dump(self, _ct: Controller) -> None:
        emit(
            unseen=Grid(
                [0.0 if e is not None else 1.0 for e in self.env],
                palette=_P_FOG,
            ),
            cost=Grid(
                [c if c < 1e6 else -1 for c in self.cost_grid],
                palette=_P_COST,
            ),
            conv_cost=Grid(
                [c if c < 1e6 else -1 for c in self.conveyor_cost_grid],
                palette=_P_COST,
            ),
            enemy_launcher=Tiles(
                [(p.x, p.y) for p in self.adjacent_to_enemy_launcher],
            ),
            unconnected_harvester=Tiles(
                [(p.x, p.y) for p in self.adjacent_to_unconnected_harvester],
            ),
            harvester_adjacent=Tiles(
                [(p.x, p.y) for p in self.adjacent_to_harvester],
            ),
            symmetry=Scalar(str(self.symmetry)),
            symmetry_candidates=Scalar(str(self.symmetry_candidates)),
            role=Scalar(str(self.role)),
            bfs_dist=Grid(self.nav_dist, palette=_P_DIST),
            bfs_parent=VectorField(_parent_to_angles(self.nav_parent, self.w)),
        )

    # ================================================================================
    #  Task: Explore
    # ================================================================================

    def _move_via_path(
        self,
        ct: Controller,
        target: Position,
        *,
        check_money: bool = True,
    ) -> None:
        path = self._extract_path(target.x, target.y)
        if path and len(path) > 1:
            w = self.w
            nx, ny = path[1] % w, path[1] // w
            next_pos = Position(nx, ny)
            if check_money and ct.get_global_resources()[0] < 75:
                dirs = DIR8
                self.rng.shuffle(dirs)
                my_pos = ct.get_position()
                for d in dirs:
                    if try_move(ct, my_pos.add(d)):
                        break
            else:
                self._try_move_with_build(ct, next_pos)

    def _explore(self, ct: Controller) -> None:
        self.scout_age += 1
        t = self.scout_target
        my_pos = ct.get_position()

        if (
            self.scout_age > 20
            or t is None
            or my_pos.distance_squared(t) < 3
            or self.get_cost(t) >= INF
        ):
            t = Position(-10, -10)
            while (
                t.x < 0
                or t.y < 0
                or t.x >= self.w
                or t.y >= self.h
                or self.get_cost(t) >= INF
            ):
                theta = self.rng.random() * math.tau
                t = Position(
                    my_pos.x + round(math.cos(theta) * self.scout_radius),
                    my_pos.y + round(math.sin(theta) * self.scout_radius),
                )
                if self.scout_radius >= self.w / 2 or self.scout_radius >= self.h / 2:
                    self.scout_radius -= 1.0

            self.scout_age = 0
            self.scout_target = t
            ct.draw_indicator_dot(t, 255, 0, 255)
            self._move_via_path(ct, t)
        else:
            ct.draw_indicator_dot(t, 10, 0, 10)
            self._move_via_path(ct, t)

    # ================================================================================
    #  Task: Harvest
    # ================================================================================

    def _ore_available(self, ct: Controller, pos: Position) -> bool:
        b = self.get_building(pos)
        if b is not None and not isinstance(b, BuildingRoad):
            return False

        if ct.is_in_vision(pos):
            worker_id = ct.get_tile_builder_bot_id(pos)
            if worker_id is not None and worker_id != ct.get_id():
                return False

        return True

    def _pick_ore_target(self, ct: Controller) -> Position | None:
        my_pos = ct.get_position()
        best_target = None
        min_dist = INF

        for pos in ct.get_nearby_tiles():
            terrain = self.get_env(pos)

            if terrain == Environment.ORE_TITANIUM:
                match self.get_building(pos):
                    case None | BuildingRoad():
                        if self._ore_available(ct, pos):
                            dist = my_pos.distance_squared(pos)
                            if dist < min_dist:
                                min_dist = dist
                                best_target = pos
                    case _:
                        continue

        return best_target

    def _build_at_ore(self, ct: Controller, target_pos: Position) -> bool:
        my_pos = ct.get_position()

        neighbors = [target_pos.add(d) for d in DIR4]
        unpaved_neighbors = []
        for n in neighbors:
            if not self.in_bounds(n):
                continue
            if self.get_env(n) == Environment.WALL:
                continue

            b = self.get_building(n)
            if b is None:
                unpaved_neighbors.append(n)
            elif not isinstance(b, BuildingRoad):
                pass

        if my_pos == target_pos:
            if not self._ore_available(ct, target_pos):
                self.ore_target = None
                return False

            for n in unpaved_neighbors:
                if n == my_pos:
                    continue
                if ct.can_build_road(n):
                    ct.build_road(n)
                    return True

            if not can_afford(ct, EntityType.HARVESTER):
                return True

            b = self.get_building(my_pos)
            if isinstance(b, BuildingRoad) and ct.can_destroy(my_pos):
                escape_tile = None
                for d in DIR4:
                    check_pos = my_pos.add(d)
                    if ct.can_move(d):
                        escape_tile = check_pos
                        break

                if escape_tile:
                    ct.destroy(my_pos)
                else:
                    return True

            preferred_dirs = []
            if self.my_core:
                path = conv_search.search(self, ct, my_pos, self.my_core)
                if path and len(path) > 1:
                    next_pos = path[1]
                    d = get_direction_object(my_pos, next_pos)
                    if d:
                        preferred_dirs.append(d)

            ortho_preferred = [d for d in preferred_dirs if d in DIR4]
            ortho_others = [d for d in DIR4 if d not in preferred_dirs]
            all_dirs = ortho_preferred + ortho_others

            for d in all_dirs:
                move_pos = my_pos.add(d)
                if self.is_passable(move_pos) and ct.can_move(d):
                    ct.move(d)
                    if ct.can_build_harvester(target_pos):
                        ct.build_harvester(target_pos)
                        self.ore_target = None
                    return True

            return True

        if my_pos.distance_squared(target_pos) <= 2:
            if unpaved_neighbors:
                for n in unpaved_neighbors:
                    if my_pos.distance_squared(n) <= 2 and ct.can_build_road(n):
                        ct.build_road(n)
                        return True

                target_has_road = isinstance(
                    self.get_building(target_pos),
                    BuildingRoad,
                )

                if target_has_road:
                    if self._try_move_with_build(ct, target_pos):
                        return True
                else:
                    target_n = unpaved_neighbors[0]
                    path = conv_search.search_blocked(self, ct, my_pos, target_n)
                    if path and len(path) > 1:
                        self._try_move_with_build(ct, path[1])
                        return True
                return True

            if not can_afford(ct, EntityType.HARVESTER):
                if self._try_move_with_build(ct, target_pos):
                    return True
                return True

            has_road = isinstance(self.get_building(target_pos), BuildingRoad)

            if has_road:
                if self._try_move_with_build(ct, target_pos):
                    return True
            elif (
                ct.can_build_harvester(target_pos)
                and my_pos.distance_squared(target_pos) <= 1
            ):
                ct.build_harvester(target_pos)
                self.ore_target = None
                return True
            else:
                if my_pos.distance_squared(target_pos) > 1:
                    for d in DIR4:
                        ortho_pos = target_pos.add(d)
                        if (
                            self.is_passable(ortho_pos)
                            and my_pos.distance_squared(ortho_pos) <= 2
                        ) and self._try_move_with_build(ct, ortho_pos):
                            return True

                    if self._try_move_with_build(ct, target_pos):
                        return True

                    return True

                if ct.can_build_harvester(target_pos):
                    ct.build_harvester(target_pos)
                    self.ore_target = None
                    return True

        return self._make_move(ct, target_pos)

    # ================================================================================
    #  Task: Heal
    # ================================================================================

    def _best_healable_building(self, ct: Controller) -> Position | None:
        best: Position | None = None
        best_score: tuple[int, int, int] = (0, 0, 0)
        for pos in self.healable_buildings:
            i = self.idx(pos)
            hp = self.hp[i]
            max_hp = self.max_hp[i]
            damage = max_hp - hp
            dist = chebyshev(ct.get_position(), pos)
            turns_to_die = hp // 2
            if damage < 5 and ct.get_position().distance_squared(pos) > 2:
                closer_friend = False
                for d in DIR8:
                    test_position = pos.add(d)
                    if self.in_bounds(test_position) and ct.is_in_vision(test_position):
                        builder = ct.get_tile_builder_bot_id(test_position)
                        if (
                            builder is not None
                            and ct.get_team(builder) == ct.get_team()
                        ):
                            closer_friend = True
                            self.ally_sightings[test_position] = ct.get_current_round()
                        elif test_position in self.ally_sightings:
                            del self.ally_sightings[test_position]
                    elif (
                        test_position in self.ally_sightings
                        and ct.get_current_round() - self.ally_sightings[test_position]
                        < 4
                    ):
                        closer_friend = True

                if closer_friend:
                    if not ct.is_in_vision(pos):
                        self.hp[i] = max_hp
                    continue

            if damage < 4:
                tier = 0
            elif turns_to_die >= dist:
                tier = 2
            else:
                tier = 1
            score = (tier, damage, turns_to_die - dist)

            if score > best_score:
                best = pos
                best_score = score
        self.healable_buildings = [
            p
            for p in self.healable_buildings
            if self.hp[self.idx(p)] < self.max_hp[self.idx(p)]
        ]
        return best

    def _best_adjacent_healable_building(self, ct: Controller) -> Position | None:
        best: Position | None = None
        best_score: tuple[int, int] = (0, 0)
        for pos in self.healable_buildings:
            i = self.idx(pos)
            hp = self.hp[i]
            max_hp = self.max_hp[i]
            damage = max_hp - hp
            if ct.get_position().distance_squared(pos) > 2:
                continue
            score = (0, damage) if damage < 4 else (1, damage)
            if score > best_score:
                best = pos
                best_score = score
        return best

    def _run_heal(self, ct: Controller) -> bool:
        if self.repair_pos and ct.is_in_vision(self.repair_pos):
            b = self.get_building(self.repair_pos)
            ti = self.idx(self.repair_pos)
            if b and self.hp[ti] < self.max_hp[ti] - 2 and b.team == ct.get_team():
                pass
            else:
                self.repair_pos = None
        repair_pos = self._best_healable_building(ct)
        if (
            repair_pos and repair_pos.distance_squared(ct.get_position()) <= 2
        ) or not self.repair_pos:
            self.repair_pos = repair_pos

        if not self.repair_pos:
            return False

        being_attacked = False
        heal_position = self.repair_pos
        if ct.is_in_vision(heal_position):
            builder = ct.get_tile_builder_bot_id(heal_position)
            being_attacked = (
                builder is not None and ct.get_team(builder) != ct.get_team()
            )

        building_to_heal = self._best_adjacent_healable_building(ct)
        save_money = being_attacked and self.repaired_prev
        if building_to_heal:
            self.repaired_prev = self._try_heal(
                ct,
                building_to_heal,
                conserve_ti=save_money,
            )
        else:
            self.repaired_prev = False
        self._make_move(ct, self.repair_pos)
        building_to_heal = self._best_adjacent_healable_building(ct)
        if building_to_heal:
            self.repaired_prev = (
                self._try_heal(ct, building_to_heal, conserve_ti=save_money)
                or self.repaired_prev
            )
        return True

    def _has_wounded_enemy(self, ct: Controller, position: Position) -> bool:
        b = self.get_building(position)
        if not b:
            return False
        i = self.idx(position)
        return b.team != ct.get_team() and self.hp[i] < self.max_hp[i]

    def _heal_adjacent_builders(self, ct: Controller) -> bool:
        adjacent_builders = ct.get_nearby_units(2)
        for eid in adjacent_builders:
            if (ct.get_hp(eid) <= ct.get_max_hp(eid) - 4) and ct.get_team(
                eid,
            ) == ct.get_team():
                position = ct.get_position(eid)
                if self._has_wounded_enemy(ct, position):
                    continue
                if self._try_heal(ct, position, conserve_ti=False):
                    return True
        return False

    def _heal_self(self, ct: Controller) -> bool:
        if ct.get_hp() > ct.get_max_hp() - 4:
            return False

        my_pos = ct.get_position()
        if not self._has_wounded_enemy(ct, my_pos):
            self._try_heal(ct, my_pos, conserve_ti=False)
            self._move_random(ct)
            return True

        for d in DIR8:
            if ct.can_move(d) and not self._has_wounded_enemy(ct, my_pos.add(d)):
                ct.move(d)
                self._try_heal(ct, ct.get_position(), conserve_ti=False)
                return True

        return False

    def _heal_builders(self, ct: Controller) -> bool:
        b = self.get_building(ct.get_position())
        if b and b.team != ct.get_team():
            i = self.idx(ct.get_position())
            if self.hp[i] <= 2:
                return False
            if self.hp[i] <= 6 and ct.get_hp() > 18:
                return False
        return bool(self._heal_adjacent_builders(ct) or self._heal_self(ct))

    # ================================================================================
    #  Task: Defend
    # ================================================================================

    @staticmethod
    def _is_turret(b: Building | None) -> bool:
        match b:
            case BuildingGunner() | BuildingSentinel():
                return True
            case _:
                return False

    @staticmethod
    def _is_turret_or_transport(b: Building | None) -> bool:
        match b:
            case (
                BuildingGunner()
                | BuildingSentinel()
                | BuildingConveyor()
                | BuildingArmouredConveyor()
                | BuildingSplitter()
                | BuildingBridge()
            ):
                return True
            case _:
                return False

    def _gunner_facing(self, ct: Controller, pos: Position) -> Direction | None:
        if not self.in_bounds(pos):
            return None
        if pos not in self.adjacent_to_harvester:
            return None
        if not self.is_buildable(pos):
            return None
        if Builder._is_turret(self.get_building(pos)):
            return None
        if not self.in_bounds(pos) or not ct.is_in_vision(pos):
            return None
        builder = ct.get_tile_builder_bot_id(pos)
        if builder is not None and builder != ct.get_id():
            return None
        for d in DIR8:
            match self.get_building(pos.add(d)):
                case BuildingGunner(team=t) | BuildingSentinel(team=t) if (
                    t != ct.get_team()
                ):
                    for harvester_direction in DIR4:
                        if harvester_direction != d:
                            match self.get_building(pos.add(harvester_direction)):
                                case BuildingHarvester():
                                    return d
        return None

    def _sentinel_facing(self, ct: Controller, pos: Position) -> Direction | None:
        if not self.in_bounds(pos):
            return None
        b = self.get_building(pos)
        if (
            not self.nearest_enemy_turret
            or pos.distance_squared(self.nearest_enemy_turret)
            > GameConstants.SENTINEL_VISION_RADIUS_SQ
            or pos not in self.adjacent_to_harvester
            or not self.is_buildable(pos)
            or Builder._is_turret_or_transport(b)
            or not self.in_bounds(pos)
            or not ct.is_in_vision(pos)
        ):
            return None
        builder = ct.get_tile_builder_bot_id(pos)
        if builder is not None and builder != ct.get_id():
            return None

        d = pos.direction_to(self.nearest_enemy_turret)
        found_harvester = False
        for harvester_direction in DIR4:
            if harvester_direction != d:
                match self.get_building(pos.add(harvester_direction)):
                    case BuildingHarvester():
                        found_harvester = True
        if not found_harvester:
            return None

        shootable_tiles = ct.get_attackable_tiles_from(pos, d, EntityType.SENTINEL)
        if self.nearest_enemy_turret in shootable_tiles:
            return d
        return None

    def _place_sentinel_nearby(self, ct: Controller) -> bool:
        my_pos = ct.get_position()
        for d in DIR8:
            test_position = my_pos.add(d)
            result = self._sentinel_facing(ct, test_position)
            if result is not None:
                return Builder._try_place(
                    ct,
                    EntityType.SENTINEL,
                    test_position,
                    result,
                )
        result = self._sentinel_facing(ct, my_pos)
        if result and self._move_random(ct):
            Builder._try_place(ct, EntityType.SENTINEL, my_pos, result)
            return True
        return False

    def _place_gunner_nearby(self, ct: Controller) -> bool:
        my_pos = ct.get_position()
        for d in DIR8:
            test_position = my_pos.add(d)
            result = self._gunner_facing(ct, test_position)
            if result is not None:
                return Builder._try_place(ct, EntityType.GUNNER, test_position, result)
        result = self._gunner_facing(ct, my_pos)
        if result and self._move_random(ct):
            Builder._try_place(ct, EntityType.GUNNER, my_pos, result)
            return True
        return self._place_sentinel_nearby(ct)

    # ================================================================================
    #  Task: Build Conveyors
    # ================================================================================

    def _clear_with_turret(
        self,
        ct: Controller,
        build_pos: Position,
        target_pos: Position,
    ) -> bool:
        if build_pos == ct.get_position():
            for d in DIR8:
                if ct.can_move(d):
                    ct.move(d)
                    break

        if build_pos == ct.get_position():
            for d in DIR8:
                move_pos = ct.get_position().add(d)
                if self._try_move_with_build(ct, move_pos):
                    break

        direction = build_pos.direction_to(target_pos)
        return Builder._try_place(ct, EntityType.SENTINEL, build_pos, direction)

    def _lay_segment(
        self,
        ct: Controller,
        start_pos: Position,
        path: list[Position] | None,
    ) -> bool:
        if not path:
            return False

        bid = ct.get_tile_building_id(start_pos)
        if bid is None:
            return False
        entity_type = ct.get_entity_type(bid)
        direction: Direction | None = None
        if (
            self.my_core
            and start_pos.distance_squared(self.my_core) <= 5
            and path[-1] == self.my_core
        ):
            for d in DIR4:
                check_pos = start_pos.add(d)
                if check_pos.distance_squared(self.my_core) <= 2:
                    direction = d
                    break
        else:
            direction = get_direction_object(start_pos, path[1])

        if entity_type == EntityType.CONVEYOR:
            if ct.get_direction(bid) == direction:
                return True
        elif entity_type == EntityType.BRIDGE:
            bridge_output = ct.get_bridge_target(bid)
            if not ct.is_in_vision(bridge_output) or self.is_buildable(bridge_output):
                return True

        next_pos = path[1]
        if not ct.is_in_vision(next_pos):
            return Builder._try_place(
                ct,
                EntityType.BRIDGE,
                start_pos,
                reachable_path_end(path, start_pos, 3),
            )
        destination_building = ct.get_tile_building_id(next_pos)
        destination_team = (
            ct.get_team(destination_building) if destination_building else None
        )
        destination_is_marker = (
            ct.get_entity_type(destination_building) == EntityType.MARKER
            if destination_building
            else False
        )

        if (
            direction in DIR4
            and (
                (not destination_building)
                or destination_team == ct.get_team()
                or destination_is_marker
            )
            and self.get_env(path[1]) == Environment.EMPTY
        ):
            return Builder._try_place(ct, EntityType.CONVEYOR, start_pos, direction)
        pending_bridge = reachable_path_end(path, start_pos, 3)
        if self._is_enemy_building_at(ct, pending_bridge):
            if self._clear_with_turret(ct, start_pos, pending_bridge):
                self.branch_start = start_pos
            return False
        if Builder._try_place(ct, EntityType.BRIDGE, start_pos, pending_bridge):
            if chebyshev(pending_bridge, self.my_core) > 1:
                self.pending_bridge = pending_bridge
            return True
        return False

    def _best_junction_site(
        self,
        ct: Controller,
        path: list[Position],
    ) -> Position | None:
        for pos in path[::-1]:
            if self._can_place_junction(ct, pos):
                return pos
        return None

    def _place_junction(self, ct: Controller, pos: Position) -> bool | None:
        current_building = self.get_building(pos)
        if isinstance(current_building, BuildingSplitter):
            return True

        for d in DIR4:
            new_pos = pos.add(d)
            existing_building = self.get_building(new_pos)
            if (
                (self.get_env(new_pos) == Environment.EMPTY)
                and existing_building is None
                and ct.can_build_road(new_pos)
            ):
                ct.build_road(new_pos)
                return False

        conveyors = self.get_conveyors_to_here(pos)
        adjacent_conveyors = [c for c in conveyors if c.distance_squared(pos) <= 1]
        if len(adjacent_conveyors) > 1 or len(conveyors) < 1:
            return False
        if len(adjacent_conveyors) >= 1:
            splitter_direction = adjacent_conveyors[0].direction_to(pos)
        elif isinstance(bld_at_pos := self.get_building(pos), BuildingConveyor):
            splitter_direction = bld_at_pos.direction
        else:
            splitter_direction = Direction.NORTH

        if not can_afford(ct, EntityType.SPLITTER):
            return False
        if ct.can_destroy(pos):
            ct.destroy(pos)
        if ct.can_build_splitter(pos, splitter_direction):
            ct.build_splitter(pos, splitter_direction)
            return True
        return None

    def _route_to(
        self,
        ct: Controller,
        start: Position,
        target: Position,
    ) -> None:
        self.pending_bridge = None
        self.branch_start = None

        if start == target:
            return

        if chebyshev(start, target) <= 1 and target == self.my_core:
            return

        current_pos = ct.get_position()

        start_building = self.get_building(start)
        all_blocked = True
        if isinstance(start_building, BuildingSplitter):
            for d in DIR4:
                if d == start_building.direction.opposite():
                    continue
                new_pos = start.add(d)
                if self.is_buildable(new_pos):
                    start = new_pos
                    all_blocked = False
                    break
        else:
            all_blocked = False

        existing_path = self._trace_upstream(start)
        if len(existing_path) < 1:
            return

        if self.is_friendly_turret(start) or all_blocked:
            split_location = self._best_junction_site(ct, existing_path)
            if split_location:
                self._make_move(ct, split_location)
                if self._place_junction(ct, split_location):
                    self.branch_start = split_location
                else:
                    self.branch_start = start
            return

        if not self.is_passable(start):
            if len(existing_path) > 1:
                start = existing_path[-2]
            else:
                return

        path = conv_search.search(self, ct, start, target)
        if path:
            path_start_index = 0
            for i, pos in enumerate(path):
                if pos in existing_path:
                    start = pos
                    path_start_index = i
            path = path[path_start_index:]

        if chebyshev(current_pos, start) <= 1:
            if (
                not path
                or (
                    conv_search.no_path
                    and conv_search._prev_target == target
                    and not path
                )
                or len(path) < 2
            ):
                return
            self._lay_segment(ct, start, path)
        self._make_move(ct, start)
        return

    def _route_to_core(self, ct: Controller, start: Position) -> None:
        self._route_to(ct, start, self.my_core)

    # ================================================================================
    #  Task: Attack
    # ================================================================================

    @staticmethod
    def _open_tiles(
        state: Builder,
        ct: Controller,
        positions: list[Position],
    ) -> list[Position]:
        return [
            p
            for p in positions
            if state.is_passable(p)
            and (not ct.is_in_vision(p) or ct.get_tile_builder_bot_id(p) is None)
        ]

    @staticmethod
    def _is_allied_transport(
        state: Builder,
        ct: Controller,
        position: Position,
    ) -> bool:
        match state.get_building(position):
            case (
                BuildingConveyor(team=t)
                | BuildingArmouredConveyor(team=t)
                | BuildingSplitter(team=t)
                | BuildingBridge(team=t)
            ) if t == ct.get_team():
                return True
            case _:
                return False

    @staticmethod
    def _without_allied_transport(
        state: Builder,
        ct: Controller,
        positions: list[Position],
    ) -> list[Position]:
        return [
            pos for pos in positions if not Builder._is_allied_transport(state, ct, pos)
        ]

    @staticmethod
    def _buildable(state: Builder, positions: list[Position]) -> list[Position]:
        return [
            p
            for p in positions
            if state.is_buildable(p) and not state.is_friendly_turret(p)
        ]

    @staticmethod
    def _nearest_enemy_bot(ct: Controller) -> Position | None:
        builders = ct.get_nearby_units()
        builder_positions = [
            ct.get_position(uid)
            for uid in builders
            if ct.get_team(uid) != ct.get_team()
        ]
        if len(builder_positions) == 0:
            return None
        return closest(ct.get_position(), builder_positions)

    def _should_attack(self, ct: Controller, pos: Position) -> bool:
        enemy_builder = Builder._nearest_enemy_bot(ct)
        i = self.idx(pos)
        return (
            (enemy_builder is None)
            or chebyshev(ct.get_position(), enemy_builder) > 2
            or self.hp[i] <= self.max_hp[i] - 4
            or self.hp[i] <= 4
            or can_afford(ct, EntityType.HARVESTER)
        )

    def _run_attack(self, ct: Controller) -> None:
        team = ct.get_team()
        enemy_buildings = [
            p
            for p in self.nearby_buildings
            if (b := self.get_building(p)) is not None and b.team != team
        ]
        enemy_harvesters = [
            p
            for p in enemy_buildings
            if isinstance(self.get_building(p), BuildingHarvester)
        ]

        def has_open_side(position: Position) -> bool:
            for direction in DIR4:
                new_position = position.add(direction)
                occupant = 1
                if not self.in_bounds(new_position):
                    continue
                if ct.is_in_vision(new_position):
                    occupant = ct.get_tile_builder_bot_id(new_position)
                occupied = occupant is not None and occupant != ct.get_id()
                if (
                    self.is_passable(position.add(direction))
                    and not occupied
                    and not Builder._is_allied_transport(
                        self,
                        ct,
                        position.add(direction),
                    )
                ):
                    return True
            return False

        vulnerable_harvesters = [p for p in enemy_harvesters if has_open_side(p)]
        enemy_core = self._get_enemy_core_pos()

        if (self.offense_turns > 25) or (
            self.offense_target
            and ct.is_in_vision(self.offense_target)
            and (
                not self.is_enemy_building(self.offense_target)
                or (not self.is_passable(self.offense_target))
                or (
                    ct.get_tile_builder_bot_id(self.offense_target) is not None
                    and ct.get_tile_builder_bot_id(self.offense_target) != ct.get_id()
                )
            )
        ):
            self.offense_target = None
            self.offense_launcher = None
            self.offense_turns = 0
        else:
            self.offense_turns += 1

        if len(vulnerable_harvesters) > 0:
            target = closest(ct.get_position(), vulnerable_harvesters)
            assert target is not None
            on_friendly_conveyor = Builder._is_allied_transport(
                self,
                ct,
                ct.get_position(),
            )
            if (
                ct.get_position().distance_squared(target) == 1
                and not on_friendly_conveyor
            ):
                if self.is_enemy_building(ct.get_position()):
                    if self._should_attack(ct, ct.get_position()):
                        Builder._try_attack(ct)
                    self.offense_target = ct.get_position()
                    self.offense_turns = 0

                else:
                    build_position = ct.get_position()
                    self._move_random(ct)
                    direction = build_position.direction_to(enemy_core)
                    if direction == build_position.direction_to(target):
                        direction = direction.rotate_right()
                    if self.get_env(target) == Environment.ORE_TITANIUM:
                        num_existing_sentinels = 0
                        for d in DIR4:
                            nb = self.get_building(target.add(d))
                            if (
                                isinstance(nb, BuildingSentinel)
                                and nb.team == ct.get_team()
                            ):
                                num_existing_sentinels += 1
                        if num_existing_sentinels < 2:
                            Builder._try_place(
                                ct,
                                EntityType.SENTINEL,
                                build_position,
                                direction,
                            )
                        else:
                            Builder._try_place(ct, EntityType.BARRIER, build_position)
                    elif self.get_env(target) == Environment.ORE_AXIONITE:
                        Builder._try_place(ct, EntityType.BARRIER, build_position)
                    else:
                        Builder._try_place(ct, EntityType.BARRIER, build_position)
                    if ct.can_build_road(build_position):
                        ct.build_road(build_position)
                    self._scout_toward_enemy(ct)

            else:
                destination = closest(
                    ct.get_position(),
                    Builder._without_allied_transport(
                        self,
                        ct,
                        Builder._open_tiles(self, ct, [target.add(d) for d in DIR4]),
                    ),
                )
                assert destination is not None
                launcher_location = closest(
                    destination,
                    Builder._buildable(self, [ct.get_position().add(d) for d in DIR8]),
                )
                adjacent_launchers = [
                    p
                    for p in [ct.get_position().add(d) for d in DIR8]
                    if isinstance(self.get_building(p), BuildingLauncher)
                ]

                best_adjacent_launcher = closest(destination, adjacent_launchers)
                if (
                    ct.get_position().distance_squared(destination) <= 2
                    or ct.get_position().distance_squared(target) < 9
                ):
                    self._make_move(ct, destination)
                elif (
                    best_adjacent_launcher
                    and self.is_walkable(destination)
                    and best_adjacent_launcher.distance_squared(destination)
                    <= GameConstants.LAUNCHER_VISION_RADIUS_SQ
                ):
                    pass
                elif (
                    launcher_location
                    and not best_adjacent_launcher
                    and self.is_walkable(destination)
                    and launcher_location.distance_squared(destination)
                    <= GameConstants.LAUNCHER_VISION_RADIUS_SQ
                    and Builder._try_place(ct, EntityType.LAUNCHER, launcher_location)
                ):
                    self.offense_launcher = launcher_location
                elif (
                    self.offense_launcher
                    and self.offense_launcher.distance_squared(ct.get_position()) < 25
                ):
                    self._make_move(ct, self.offense_launcher)
                elif (
                    self.offense_target
                    and self.offense_target.distance_squared(ct.get_position()) < 20
                ):
                    self._make_move(ct, self.offense_target)
                else:
                    self._make_move(ct, target)

            if (
                ct.get_position().distance_squared(target) == 1
                and self.is_enemy_building(ct.get_position())
                and self._should_attack(ct, ct.get_position())
            ):
                Builder._try_attack(ct)
        elif (
            self.offense_target
            and self.offense_launcher
            and isinstance(
                rl := self.get_building(self.offense_launcher),
                BuildingLauncher,
            )
            and rl.team == ct.get_team()
            and ct.get_position().distance_squared(self.offense_target) > 8
        ):
            self._make_move(ct, self.offense_launcher)
        elif self.offense_target:
            self._make_move(ct, self.offense_target)
        else:
            self._scout_toward_enemy(ct)

    def _scout_toward_enemy(self, ct: Controller) -> None:
        en_core = self._get_enemy_core_pos()
        if ct.get_position().distance_squared(en_core) <= 20:
            self.enemy_core_seen = True

        if not self.enemy_core_seen:
            self._make_move(ct, en_core)
        elif ct.get_position().distance_squared(
            en_core,
        ) <= 20 or ct.get_global_resources()[0] >= (
            GameConstants.HARVESTER_BASE_COST[0] + 50
        ) * (1 + ct.get_scale_percent() / 100):
            self._explore(ct)
        else:
            dir8 = DIR8[:]
            self.rng.shuffle(dir8)
            my_pos = ct.get_position()
            for d in dir8:
                if try_move(ct, my_pos.add(d)):
                    break

    # ================================================================================
    #  Task: Patrol
    # ================================================================================

    def _patrol_trace_upstream(self, position: Position) -> list[Position]:
        path: list[Position] = []
        conveyors = [position]
        while len(conveyors) > 0:
            self.rng.shuffle(conveyors)
            position = conveyors[0]
            conveyors = self.get_conveyors_to_here(position)
            if position in path:
                break
            path.append(position)
        return path

    def _core_feeders(self) -> list[Position]:
        return [
            pos
            for d in Direction
            for pos in self.get_conveyors_to_here(self.my_core.add(d))
        ]

    def _run_patrol(self, ct: Controller) -> bool:
        my_pos = ct.get_position()
        patrol_range = 4
        if self.patrol_head:
            if my_pos.distance_squared(self.patrol_head) > patrol_range:
                self._make_move(ct, self.patrol_head)
                return True
            conveyors = self.get_conveyors_to_here(self.patrol_head)
            if len(conveyors) == 0:
                self.patrol_head = None
                self.patrol_trail = []
                self._make_move(ct, self.my_core)
                return True
            while (
                len(conveyors) > 0
                and my_pos.distance_squared(self.patrol_head) <= patrol_range
            ):
                self.rng.shuffle(conveyors)
                self.patrol_head = conveyors[0]
                conveyors = self.get_conveyors_to_here(self.patrol_head)
                if self.patrol_head in self.patrol_trail:
                    self.patrol_head = None
                    self.patrol_trail = []
                    self._make_move(ct, self.my_core)
                    return True
                self.patrol_trail.append(self.patrol_head)
            self._make_move(ct, self.patrol_head)
            return True
        if my_pos == self.my_core or (
            my_pos.distance_squared(self.my_core) <= 8
            and not ct.can_move(my_pos.direction_to(self.my_core))
        ):
            conveyors = self._core_feeders()
            if len(conveyors) > 0:
                self.rng.shuffle(conveyors)
                self.patrol_head = conveyors[0]
                self.patrol_trail = []
                self._make_move(ct, self.patrol_head)
                return True
            return False
        self._make_move(ct, self.my_core)
        return True

    # ================================================================================
    #  Task: Extra (Fix Enemy Conveyor, Pave Near Harvesters)
    # ================================================================================

    def _fix_enemy_conveyor(self, ct: Controller) -> bool:
        nearby_positions = ct.get_nearby_tiles(2)
        for pos in nearby_positions:
            if self.leads_to_enemy_building(pos) and ct.can_destroy(pos):
                ct.destroy(pos)
                if ct.can_build_road(pos):
                    ct.build_road(pos)
                    return True
        return False

    def _pave_near_harvesters(self, ct: Controller) -> bool:
        nearby_positions = ct.get_nearby_tiles(2)
        for pos in nearby_positions:
            if (
                pos in self.adjacent_to_harvester
                and not self.get_building(pos)
                and self.get_env(pos) != Environment.WALL
            ):
                if self._is_dangling(ct, pos):
                    self._route_to_core(ct, pos)
                    return True
                if ct.can_build_road(pos):
                    ct.build_road(pos)
                    return True
        return False

    # ================================================================================
    #  Policy Dispatch & Main Loop
    # ================================================================================

    def _connect_close(self, ct: Controller) -> bool:
        my_pos = ct.get_position()
        if self.branch_start and my_pos.distance_squared(self.branch_start) <= 2:
            self._route_to_core(ct, self.branch_start)
            return True
        if self.dangling_output and my_pos.distance_squared(self.dangling_output) <= 2:
            self._route_to_core(ct, self.dangling_output)
            return True
        return False

    def _connect_far(self, ct: Controller) -> bool:
        if self.branch_start:
            self._route_to_core(ct, self.branch_start)
            return True
        if self.dangling_output:
            self._route_to_core(ct, self.dangling_output)
            return True
        return False

    def _heal(self, ct: Controller) -> bool:
        return self._run_heal(ct) or self._heal_builders(ct)

    def _patrol_cheap(self, ct: Controller) -> bool:
        return (
            self.role == Role.DEFENSE
            and not can_afford(ct, EntityType.HARVESTER)
            and self._run_patrol(ct)
        )

    def _harvest(self, ct: Controller) -> bool:
        return self.ore_target is not None and self._build_at_ore(ct, self.ore_target)

    def _patrol_late(self, ct: Controller) -> bool:
        return (
            self.role == Role.DEFENSE
            and len(self.adjacent_to_harvester) > 0
            and self._run_patrol(ct)
        )

    def _opportunistic_attack(self, ct: Controller) -> bool:
        if (
            self.opportunistic
            and self.rng.random() < 0.2
            and ct.get_current_round() > 100
            and ct.can_fire(ct.get_position())
            and ct.get_team(ct.get_tile_building_id(ct.get_position())) != ct.get_team()
        ):
            ct.fire(ct.get_position())
            return True
        return False

    def _task_explore(self, ct: Controller) -> bool:
        if ct.get_global_resources()[0] <= 100:
            return False
        self._explore(ct)
        return True

    def _task_wander(self, ct: Controller) -> bool:
        dir8 = DIR8[:]
        self.rng.shuffle(dir8)
        my_pos = ct.get_position()
        for d in dir8:
            if try_move(ct, my_pos.add(d)):
                return True
        return any(self._try_move_with_road(ct, my_pos.add(d)) for d in dir8)

    def _attack(self, ct: Controller) -> bool:
        self._run_attack(ct)
        return True

    def _end_of_turn_heal(self, ct: Controller) -> None:
        my_pos = ct.get_position()
        nearby_units = [
            unit
            for unit in ct.get_nearby_units()
            if (ct.get_position(unit).distance_squared(my_pos) <= 2)
            or (ct.get_entity_type(unit) == EntityType.CORE)
        ]

        current_position = ct.get_position()
        if ct.can_heal(current_position) and ct.get_hp() < ct.get_max_hp():
            ct.heal(current_position)
        for unit in nearby_units:
            if ct.get_entity_type(unit) == EntityType.CORE:
                core_center = ct.get_position(unit)
                for d in DIR8:
                    heal_pos = core_center.add(d)
                    if (
                        ct.can_heal(heal_pos)
                        and ct.get_team(unit) == ct.get_team()
                        and ct.get_hp(unit) < ct.get_max_hp(unit)
                    ):
                        ct.heal(heal_pos)

            if (
                ct.can_heal(ct.get_position(unit))
                and ct.get_team(unit) == ct.get_team()
                and ct.get_hp(unit) < ct.get_max_hp(unit)
            ):
                ct.heal(ct.get_position(unit))

    @override
    def run(self, ct: Controller) -> None:
        t0 = ct.get_cpu_time_elapsed()
        self._update_map(ct)
        t1 = ct.get_cpu_time_elapsed()
        print(f"  map={t1 - t0}us")
        self._update_splittable_locations(ct)
        t2 = ct.get_cpu_time_elapsed()
        print(f"  splittable={t2 - t1}us")
        self._update_role(ct)
        t3 = ct.get_cpu_time_elapsed()
        print(f"  role={t3 - t2}us")
        self._update_bfs(ct)
        t3b = ct.get_cpu_time_elapsed()
        print(f"  bfs={t3b - t3}us")
        print(f"update={t3b - t0}us")

        if DEBUG_DUMP:
            self._dump(ct)

        if self.role != Role.OFFENSE:
            self._update_economy(ct)
            t4 = ct.get_cpu_time_elapsed()
            print(f"  econ={t4 - t3}us")
        else:
            t4 = t3

        assert self.role is not None
        policies: dict[Role, list[Callable[[Builder, Controller], bool]]] = {
            Role.OFFENSE: [
                Builder._heal,
                Builder._attack,
            ],
            Role.ECON: [
                Builder._place_gunner_nearby,
                Builder._fix_enemy_conveyor,
                Builder._pave_near_harvesters,
                Builder._connect_close,
                Builder._heal,
                Builder._connect_far,
                Builder._harvest,
                Builder._opportunistic_attack,
                Builder._task_explore,
                Builder._task_wander,
            ],
            Role.DEFENSE: [
                Builder._place_gunner_nearby,
                Builder._fix_enemy_conveyor,
                Builder._pave_near_harvesters,
                Builder._connect_close,
                Builder._heal,
                Builder._connect_far,
                Builder._patrol_cheap,
                Builder._harvest,
                Builder._patrol_late,
                Builder._opportunistic_attack,
                Builder._task_explore,
                Builder._task_wander,
            ],
        }
        for task in policies[self.role]:
            if task(self, ct):
                break

        if self.role != Role.OFFENSE:
            self._end_of_turn_heal(ct)

        t5 = ct.get_cpu_time_elapsed()
        print(f"task={t5 - t4}us")
        print(f"total={t5 - t0}us")
