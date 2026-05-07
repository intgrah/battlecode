from __future__ import annotations

from collections import deque
from collections.abc import Callable
from random import Random

PosInt = int

from building import (
    Building,
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingRoad,
    BuildingSplitter,
)
from cambc import Controller, EntityType, Environment, Position, Team
from config import DEBUG_DUMP, DEBUG_TASK, DEBUG_TIMING, DEBUG_ASSERT
from unit import Unit
from util import DIR8, INF, DELTA_TO_DIR, Symmetry, can_afford, try_move

from .algorithms.nav_bfs import NavBfs, PassableGrid
from .dump import dump
from .extra import deny_enemy_ore, fix_enemy_conveyor, pave_near_harvesters
from .flow import Flow, FlowValue
from .helpers import try_move_with_road
from .role import Role
from .task_build_conveyors import route_to_core
from .task_defend import place_gunner_nearby
from .task_explore import explore
from .task_harvest import build_at_ore
from .task_heal import heal_builders, run_heal
from .task_patrol import run_patrol
from .update.econ import update_economy, update_role
from .update.map import can_place_junction, update_map, update_splittable_locations

__all__ = ["Builder"]

_MAX_MAP: int = 50  # max map dimension per game rules (maps are 20×20 to 50×50)

WALKABLE_ENTITIES = [
    EntityType.CONVEYOR,
    EntityType.ROAD,
    EntityType.SPLITTER,
    EntityType.ARMOURED_CONVEYOR,
    EntityType.BRIDGE,
]

TaskFn = Callable[["Builder", Controller], bool]


def _connect_close(self: Builder, ct: Controller) -> bool:
    if self.branch_start >= 0 and self.my_sq_dist(self.branch_start) <= 2:
        route_to_core(self, ct, self.branch_start)
        return True
    if self.dangling_output >= 0 and self.my_sq_dist(self.dangling_output) <= 2:
        route_to_core(self, ct, self.dangling_output)
        return True
    return False


def _connect_far(self: Builder, ct: Controller) -> bool:
    if self.branch_start >= 0:
        route_to_core(self, ct, self.branch_start)
        return True
    if self.dangling_output >= 0:
        route_to_core(self, ct, self.dangling_output)
        return True
    return False


def _heal(self: Builder, ct: Controller) -> bool:
    return run_heal(self, ct) or heal_builders(self, ct)


def _patrol_cheap(self: Builder, ct: Controller) -> bool:
    return not can_afford(ct, EntityType.HARVESTER) and run_patrol(self, ct)


def _harvest(self: Builder, ct: Controller) -> bool:
    return self.ore_target >= 0 and build_at_ore(self, ct, self.ore_target)


def _patrol_late(self: Builder, ct: Controller) -> bool:
    return bool(self.adjacent_to_harvester) and run_patrol(self, ct)


def _opportunistic_attack(self: Builder, ct: Controller) -> bool:
    if (
        self.opportunistic
        and self.rng.random() < 0.2
        and self.rnd > 100
        and ct.can_fire(self.pos(self.my_pos))
        and ct.get_team(ct.get_tile_building_id(self.pos(self.my_pos))) != self.my_team
    ):
        ct.fire(self.pos(self.my_pos))
        return True
    return False


def _explore(self: Builder, ct: Controller) -> bool:
    if ct.get_global_resources()[0] <= 100:
        return False
    explore(self, ct)
    return True


def _wander(self: Builder, ct: Controller) -> bool:
    dir8 = list(DIR8)
    self.rng.shuffle(dir8)
    my_pos = self.my_pos
    for d in dir8:
        if try_move(self, ct, my_pos + d):
            return True
    return any(try_move_with_road(self, ct, my_pos + d) for d in dir8)


def _attack(self: Builder, ct: Controller) -> bool:
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

    def __init__(self) -> None:
        # Pre-allocate using worst-case map size so Player.__init__ can
        # call this without a Controller. Builder.init() fills in actual
        # dimensions and player-specific state on first run().

        self.my_team: Team = Team.A
        self.my_core: PosInt = -1
        self.my_pos: PosInt = -1
        self.my_id: int = 0
        self.rnd: int = 0
        self.rng: Random = Random(0)
        self.dump_path: list[PosInt] | None = None

        # Padded cost-grid dimensions. A 3-tile border on every side
        # gives A* unconditional neighbor lookups for the bridge
        # r²≤9 set — any out-of-bounds neighbor lands on the padding
        # which is permanently INF, so the inner loop drops bounds
        # checks entirely. Only `cost_grid` and `conveyor_cost_grid`
        # use the padded layout; env/buildings/hp/... stay real-sized.
        self.pad: int = 3
        self.pw: int = 50 + 2 * self.pad
        self.ph: int = 50 + 2 * self.pad
        pn = self.pw * self.ph

        # Distances assume positions encoded as y * dist_stride + x.
        # Stride = 2w (not w) so that p-q uniquely determines (dy, dx):
        # max |dx| is w-1, so |dx2-dx1| < 2w = stride, avoiding the
        # collisions that would otherwise let a y-borrow alias a
        # smaller x-delta onto the same p-q value.
        # dist_stride stays fixed at 2*_MAX_MAP even after init() sets
        # self.w to the real width — all arrays are sized for worst-case.
        self.dist_stride: int = 2 * 50
        max_delta: int = (50 - 1) * self.dist_stride + (50 - 1)
        self.dist_offset: int = max_delta
        dist_size: int = 2 * max_delta + 1
        # Eagerly precompute all distances for every (dy, dx) reachable
        # on a _MAX_MAP × _MAX_MAP grid. Smaller maps are a strict subset
        # of this range so no lazy fallback is needed.
        self.dist_sq: list[int] = [0] * dist_size
        self.manhat: bytearray = bytearray(dist_size)
        self.chebyshev: bytearray = bytearray(dist_size)
        s = self.dist_stride
        for dy in range(-(50 - 1), 50):
            for dx in range(-(50 - 1), 50):
                i = dy * s + dx + max_delta
                adx = dx if dx >= 0 else -dx
                ady = dy if dy >= 0 else -dy
                self.dist_sq[i] = dx * dx + dy * dy
                self.manhat[i] = adx + ady
                self.chebyshev[i] = adx if adx > ady else ady
        self.bound_range: int = self.dist_stride * 50
        self.posint_valid: bytearray = bytearray(self.bound_range)

        # Per-tile arrays (indexed by PosInt = y * dist_stride + x).
        # Sized to bound_range so PosInt lookups never need bounds
        # adjustment; half the slots are "holes" (x in [w, 2w)) and
        # stay at their initial value forever.
        self.env: list[Environment | None] = [None] * self.bound_range
        self.buildings: list[Building | None] = [None] * self.bound_range
        self.hp: list[int] = [0] * self.bound_range
        self.max_hp: list[int] = [0] * self.bound_range
        # Padded cost grids: border = INF, interior initialised to
        # the default cost for an unseen tile. Real tile (x, y) lives
        # at padded index (y + pad) * pw + (x + pad).
        self.conveyor_cost_grid: list[int] = [INF] * pn
        # Per-bot adgato-style passability grid + BFS navigator for
        # movement. Shared across all `move_search` calls for this
        # bot (which is why NavBfs lives on State, not at module
        # level like v54's old AStarSearch singletons).
        # Re-created in init() with actual map dimensions.
        self.pass_grid: PassableGrid = PassableGrid(50, 50)
        self.nav: NavBfs = NavBfs(self.pass_grid)

        self.conveyors_to_here: list[list[PosInt]] = [
            [] for _ in range(self.bound_range)
        ]
        self.splitters_to_here: list[list[PosInt]] = [
            [] for _ in range(self.bound_range)
        ]

        # Symmetry
        self.symmetry_candidates: set[Symmetry] = {
            Symmetry.ROT,
            Symmetry.HOR,
            Symmetry.VER,
        }
        self.symmetry: Symmetry | None = None
        self.reflect_queue: deque[int] = deque()

        # Ephemeral (recomputed each turn)
        self.nearby_positions: list[PosInt] = []
        self.nearby_buildings: list[PosInt] = []
        self.healable_buildings: list[PosInt] = []
        self.adjacent_to_unconnected_harvester: set[PosInt] = set()
        self.adjacent_to_harvester: set[PosInt] = set()
        self.adjacent_to_enemy_launcher: set[PosInt] = set()
        # Tiles that are in the forward firing ray of an enemy gunner
        # or sentinel. Populated per-turn in state_update_map when a
        # visible enemy turret is encountered. Used as a soft cost
        # penalty in cost_grid so move_search routes bots around them.
        self.enemy_turret_ray_tiles: set[PosInt] = set()
        # Forward firing ray of FRIENDLY gunners/sentinels. Walking
        # into one blocks our own shot for that turn — same soft
        # penalty keeps bots off their own turrets' kill lanes.
        self.friendly_turret_ray_tiles: set[PosInt] = set()
        # Ore-denial tiles: for ores in our vision whose cardinal-8
        # halo contains an enemy bot or building, the ore's 4 cardinal
        # neighbours are candidate road-placement tiles. We pave them
        # with cheap roads (1 Ti base) to deny the enemy a harvester
        # feed position before they get one built.
        self.deny_ore_neighbours: set[PosInt] = set()
        self.nearest_enemy_turret: PosInt | None = None
        self.nearest_junction_site: PosInt | None = None

        # Role
        self.role: Role | None = None
        self.role_age: int = 0
        self.permanent_role: bool = False
        self.opportunistic: bool = False  # set in init()

        # Economy
        self.ore_target: PosInt = -1
        self.pending_bridge: PosInt = -1
        self.dangling_output: PosInt = -1
        self.dangling_flow: FlowValue = FlowValue()
        self.branch_start: PosInt = -1
        self.income_window: list[int] = [0] * 16
        self.spawned: int = 0
        self.ti_ore: set[PosInt] = set()
        self.ax_ore: set[PosInt] = set()
        self.flow: list[Flow] = [Flow(0, None) for _ in range(self.bound_range)]

        # Repair
        self.repair_pos: PosInt = -1
        self.repaired_prev: bool = True
        self.ally_sightings: dict = {}

        # Offense
        self.enemy_core_seen: bool = False
        self.offense_target: PosInt = -1
        self.offense_turns: int = 0
        self.offense_launcher: PosInt = -1
        # Track the tile we last fired at, plus the HP we expected to
        # see on the building there NEXT turn (i.e. pre-fire HP minus
        # our 2 dmg). If we revisit and the tile's current HP is
        # higher than that expectation, an enemy builder healed it —
        # concrete evidence we're being out-healed on this tile.
        self.last_fire_pos: PosInt = -1
        self.last_fire_expected_hp: int = 0
        # Tiles we just got out-healed on: {tile: remaining_turns}.
        # Decremented at the top of run_attack; _pick_attack_destination
        # skips any entry still present. Stops the bounce loop where
        # we rotate around the same harvester's neighbours turn after
        # turn because the picker keeps picking one of a handful of
        # valid tiles and a nearby enemy builder just heals us off it.
        self.attack_tile_blacklist: dict[PosInt, int] = {}

        # Patrol
        self.patrol_head: PosInt = -1
        self.patrol_queue: list[tuple[PosInt, int, float]] = []

        # Scouting
        self.scout_active: bool = False
        self.scout_direction: int | None = None
        self.scout_target: PosInt = -1
        self.scout_age: int = 0
        self.scout_radius: float = 10.0
        self.scout_initial_target: PosInt = -1
        self.scout_initial_age: int = 0
        self.scout_initial_radius: float = 10.0

    def init(self, ct: Controller) -> None:
        """Called on first run(). Sets actual map dimensions and player state."""
        self.w = ct.get_map_width()
        self.h = ct.get_map_height()
        self.my_team = ct.get_team()
        self.my_core = self._idx(Builder.find_core(ct))
        self.my_pos = self._idx(ct.get_position())
        self.my_id = ct.get_id()
        self.rnd = ct.get_current_round()
        self.rng = Random(self.my_id)
        self.opportunistic = self.rng.random() < 0.5
        # Recompute padded dimensions for actual map size.
        # dist_stride stays at 2*_MAX_MAP — arrays are already sized for it.
        self.pw = self.w + 2 * self.pad
        self.ph = self.h + 2 * self.pad

        pad = self.pad
        pw = self.pw
        w = self.w
        h = self.h

        self.pass_grid.init(w, h)
        # cost_grid interior default: 1 (seen-empty equivalent, will
        # be overwritten when tiles come into vision).
        # conveyor_cost_grid interior default: 5 (unseen penalty so
        # A* doesn't plan long fog detours through unmapped terrain).
        ccg = self.conveyor_cost_grid
        valid = self.posint_valid
        for y in range(h):
            row_start = (y + pad) * pw + pad
            base = y * self.dist_stride
            for x in range(w):
                ccg[row_start + x] = 5
                valid[base + x] = 1

    def my_sq_dist(self, p: PosInt) -> int:
        return self.dist_sq[p - self.my_pos + self.dist_offset]

    def sq_dist(self, p: PosInt, q: PosInt) -> int:
        return self.dist_sq[p - q + self.dist_offset]

    def mt_dist(self, p: PosInt, q: PosInt) -> int:
        return self.manhat[p - q + self.dist_offset]

    def cv_dist(self, p: PosInt, q: PosInt) -> int:
        return self.chebyshev[p - q + self.dist_offset]

    def pos(self, i: PosInt) -> Position:
        return Position(i % self.dist_stride, i // self.dist_stride)

    def _idx(self, pos: Position) -> PosInt:
        return pos.y * self.dist_stride + pos.x

    def _pidx(self, pos: Position) -> int:
        """Padded flat index for cost_grid / conveyor_cost_grid."""
        return (pos.y + self.pad) * self.pw + (pos.x + self.pad)

    def in_bounds(self, p: PosInt) -> bool:
        return 0 <= p < self.bound_range and bool(self.posint_valid[p])

    def get_env(self, p: PosInt) -> Environment | None:
        if self.in_bounds(p):
            return self.env[p]
        return None

    def get_building(self, p: PosInt) -> Building | None:
        if self.in_bounds(p):
            return self.buildings[p]
        return None

    def get_cost(self, p: PosInt) -> int:
        if self.in_bounds(p):
            s = self.dist_stride
            x, y = p % s, p // s
            return bool(self.pass_grid.passable[(y + 1) * self.pass_grid.pw + (x + 1)])
        return INF

    def get_flow(self, p: PosInt) -> FlowValue:
        if not self.in_bounds(p):
            return FlowValue(0, 0, 0)
        return self.flow[p].get_flow()

    def has_flow(self, p: PosInt) -> bool:
        if not self.in_bounds(p):
            return False
        return self.flow[p].has_flow()

    def is_passable(self, p: PosInt) -> bool:
        if self.in_bounds(p):
            s = self.dist_stride
            x, y = p % s, p // s
            return bool(self.pass_grid.passable[(y + 1) * self.pass_grid.pw + (x + 1)])
        return False

    def is_walkable(self, p: PosInt) -> bool | None:
        if not self.is_passable(p):
            return False
        match self.get_building(p):
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

    def get_conveyors_to_here(self, p: PosInt) -> list[PosInt]:
        return self.conveyors_to_here[p] if self.in_bounds(p) else []

    def is_buildable(self, p: PosInt) -> bool:
        if self.in_bounds(p):
            b = self.buildings[p]
            return self.env[p] != Environment.WALL and (
                b is None or b.team == self.my_team
            )
        return False

    def is_friendly_turret(self, p: PosInt) -> bool:
        if not self.in_bounds(p):
            return False
        b = self.buildings[p]
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

    def is_enemy_building(self, p: PosInt) -> bool:
        if self.in_bounds(p):
            b = self.buildings[p]
            return b is not None and b.team != self.my_team
        return False

    def leads_to_enemy_building(self, p: PosInt) -> bool:
        if not self.in_bounds(p):
            return False
        b = self.buildings[p]
        if b is None or b.team != self.my_team:
            return False
        match b:
            case BuildingConveyor(direction=d):
                return self.is_enemy_building(p + d)
            case BuildingBridge(target=t):
                return self.is_enemy_building(t)
            case _:
                return False

    update_map = update_map
    update_splittable_locations = update_splittable_locations
    can_place_junction = can_place_junction
    update_role = update_role
    update_economy = update_economy
    dump = dump

    def run(self, ct: Controller) -> None:

        self.my_pos = self._idx(ct.get_position())
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

        if self.role is not None:
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
            assert self._idx(ct.get_position()) == self.my_pos
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
                heal_pos = core_center.add(DELTA_TO_DIR[d])
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
