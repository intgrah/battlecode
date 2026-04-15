from __future__ import annotations

from collections import deque
from collections.abc import Callable
from random import Random

from building import (
    Building,
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingRoad,
    BuildingSplitter,
)
from cambc import Controller, EntityType, Environment, Position
from config import DEBUG_DUMP, DEBUG_TASK, DEBUG_TIMING, DEBUG_ASSERT
from unit import Unit
from util import DIR8, INF, Symmetry, can_afford, try_move

from .algorithms.nav_bfs import NavBfs, PassableGrid
from .dump import dump
from .extra import deny_enemy_ore, fix_enemy_conveyor, pave_near_harvesters
from .flow import Flow, FlowValue
from .helpers import try_move_with_road
from .role import Role
from .task_attack import run_attack
from .task_build_conveyors import route_to_core
from .task_defend import place_gunner_nearby
from .task_explore import explore
from .task_harvest import build_at_ore
from .task_heal import heal_builders, run_heal
from .task_patrol import run_patrol
from .update.econ import update_economy, update_role
from .update.map import can_place_junction, update_map, update_splittable_locations

__all__ = ["Builder"]

WALKABLE_ENTITIES = [
    EntityType.CONVEYOR,
    EntityType.ROAD,
    EntityType.SPLITTER,
    EntityType.ARMOURED_CONVEYOR,
    EntityType.BRIDGE,
]

TaskFn = Callable[["Builder", Controller], bool]


def _connect_close(self: Builder, ct: Controller) -> bool:
    my_pos = self.my_pos
    if self.branch_start and my_pos.distance_squared(self.branch_start) <= 2:
        route_to_core(self, ct, self.branch_start)
        return True
    if self.dangling_output and my_pos.distance_squared(self.dangling_output) <= 2:
        route_to_core(self, ct, self.dangling_output)
        return True
    return False


def _connect_far(self: Builder, ct: Controller) -> bool:
    if self.branch_start:
        route_to_core(self, ct, self.branch_start)
        return True
    if self.dangling_output:
        route_to_core(self, ct, self.dangling_output)
        return True
    return False


def _heal(self: Builder, ct: Controller) -> bool:
    return run_heal(self, ct) or heal_builders(self, ct)


def _patrol_cheap(self: Builder, ct: Controller) -> bool:
    return not can_afford(ct, EntityType.HARVESTER) and run_patrol(self, ct)


def _harvest(self: Builder, ct: Controller) -> bool:
    return self.ore_target is not None and build_at_ore(self, ct, self.ore_target)


def _patrol_late(self: Builder, ct: Controller) -> bool:
    return self.adjacent_to_harvester and run_patrol(self, ct)


def _opportunistic_attack(self: Builder, ct: Controller) -> bool:
    if (
        self.opportunistic
        and self.rng.random() < 0.2
        and self.rnd > 100
        and ct.can_fire(self.my_pos)
        and ct.get_team(ct.get_tile_building_id(self.my_pos)) != self.my_team
    ):
        ct.fire(self.my_pos)
        return True
    return False


def _explore(self: Builder, ct: Controller) -> bool:
    if ct.get_global_resources()[0] <= 100:
        return False
    explore(self, ct)
    return True


def _wander(self: Builder, ct: Controller) -> bool:
    dir8 = DIR8[:]
    self.rng.shuffle(dir8)
    my_pos = self.my_pos
    for d in dir8:
        if try_move(self, ct, my_pos.add(d)):
            return True
    return any(try_move_with_road(self, ct, my_pos.add(d)) for d in dir8)


def _attack(self: Builder, ct: Controller) -> bool:
    run_attack(self, ct)
    return True


OFFENSE_TASKS: list[TaskFn] = [
    _heal,
    deny_enemy_ore,
    _attack,
]

ECON_TASKS: list[TaskFn] = [
    place_gunner_nearby,
    fix_enemy_conveyor,
    pave_near_harvesters,
    _connect_close,
    _heal,
    _connect_far,
    _harvest,
    _opportunistic_attack,
    _explore,
    _wander,
]

DEFENSE_TASKS: list[TaskFn] = [
    place_gunner_nearby,
    fix_enemy_conveyor,
    pave_near_harvesters,
    _connect_close,
    _heal,
    _connect_far,
    _patrol_cheap,
    _harvest,
    _patrol_late,
    _opportunistic_attack,
    _explore,
    _wander,
]

POLICIES: dict[Role, list[TaskFn]] = {
    Role.OFFENSE: OFFENSE_TASKS,
    Role.ECON: ECON_TASKS,
    Role.DEFENSE: DEFENSE_TASKS,
}


class Builder(Unit):
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
        self.my_core: Position = Builder.find_core(ct)
        self.my_pos: Position = ct.get_position()
        self.my_id: int = ct.get_id()
        self.rnd: int = ct.get_current_round()
        self.rng = Random(self.my_id)
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
        self.ti_ore: set[Position] = set()
        self.ax_ore: set[Position] = set()
        self.flow: list[Flow] = [Flow(0, None) for _ in range(n)]

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
        self.patrol_queue: list[tuple[Position, int, float]] = []

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

    def get_flow(self, pos: Position) -> FlowValue:
        if not self.in_bounds(pos):
            return (0, 0, 0)
        return self.flow[self._idx(pos)].get_flow()

    def has_flow(self, pos: Position) -> bool:
        if not self.in_bounds(pos):
            return False
        return self.flow[self._idx(pos)].has_flow()

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
        return self.conveyors_to_here[self._idx(pos)] if self.in_bounds(pos) else []

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

    update_map = update_map
    update_splittable_locations = update_splittable_locations
    can_place_junction = can_place_junction
    update_role = update_role
    update_economy = update_economy
    dump = dump

    def run(self, ct: Controller) -> None:

        self.my_pos = ct.get_position()
        self.rnd = ct.get_current_round()

        if DEBUG_TIMING:
            t0 = ct.get_cpu_time_elapsed()
            self.update_map(ct)
            t1 = ct.get_cpu_time_elapsed()
            print(f"  map={t1 - t0}us")
            self.update_splittable_locations(ct)
            t2 = ct.get_cpu_time_elapsed()
            print(f"  splittable={t2 - t1}us")
            self.update_role(ct)
            t3 = ct.get_cpu_time_elapsed()
            print(f"  role={t3 - t2}us")
            print(f"update={t3 - t0}us")
        else:
            self.update_map(ct)
            self.update_splittable_locations(ct)
            self.update_role(ct)

        if self.role != Role.OFFENSE:
            if DEBUG_TIMING:
                self.update_economy(ct)
                t4 = ct.get_cpu_time_elapsed()
                print(f"  econ={t4 - t3}us")
            else:
                self.update_economy(ct)
        elif DEBUG_TIMING:
            t4 = t3

        for task in POLICIES[self.role]:
            if task(self, ct):
                if DEBUG_TASK:
                    print(f"role={self.role}")
                    print(f"task={task.__name__}")
                break

        if self.role != Role.OFFENSE:
            _end_of_turn_heal(ct)

        if DEBUG_TIMING:
            t5 = ct.get_cpu_time_elapsed()
            print(f"task={t5 - t4}us")
            print(f"total={t5 - t0}us")

        if DEBUG_DUMP:
            self.dump(ct)

        if DEBUG_ASSERT:
            assert ct.get_position() == self.my_pos
            assert ct.get_team() == self.my_team
            assert ct.get_id() == self.my_id
            assert ct.get_current_round() == self.rnd

def _end_of_turn_heal(ct: Controller) -> None:
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
