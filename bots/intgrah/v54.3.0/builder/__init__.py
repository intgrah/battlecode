from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Final, override

from building import (
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingRoad,
    BuildingSplitter,
)
from cambc import (
    Controller,
    EntityType,
    Environment,
    Position,
    ResourceType,
)
from config import DEBUG_DUMP
from unit import Unit
from util import DIR8, DIR8_DELTA, INF, Symmetry

from builder.algorithms.astar import MoveHeapAstar
from builder.algorithms.bfs import extract_path, update_bfs
from builder.algorithms.econ_astar import AStarSearch
from builder.dump import dump
from builder.extra import deny_enemy_ore, fix_enemy_conveyor, pave_near_harvesters
from builder.helpers import can_afford, try_move_dir, try_move_with_road
from builder.role import Role
from builder.task_attack import run_attack
from builder.task_build_conveyors import route_to_core
from builder.task_defend import place_gunner_nearby
from builder.task_explore import explore
from builder.task_harvest import build_at_ore
from builder.task_heal import heal_builders, run_heal
from builder.task_patrol import run_patrol
from builder.update import update
from builder.update.econ import (
    can_place_junction,
    update_dangling,
    update_map_econ,
    update_ore_target,
)
from builder.update.prune import prune_stale
from builder.update.role import update_role
from builder.update.turrets import update_enemy_turrets, update_ore_denial
from builder.update.vision import update_vision

if TYPE_CHECKING:
    from collections.abc import Callable

    from building import Building


def _connect_close(self: Builder, ct: Controller) -> bool:
    if self.branch_start and self.my_pos.distance_squared(self.branch_start) <= 2:
        route_to_core(self, ct, self.branch_start)
        return True
    if self.dangling_output and self.my_pos.distance_squared(self.dangling_output) <= 2:
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
    return (
        self.role == Role.DEFENSE
        and not can_afford(self, EntityType.HARVESTER)
        and run_patrol(self, ct)
    )


def _harvest(self: Builder, ct: Controller) -> bool:
    return self.ore_target is not None and build_at_ore(self, ct, self.ore_target)


def _patrol_late(self: Builder, ct: Controller) -> bool:
    return (
        self.role == Role.DEFENSE
        and len(self.adjacent_to_harvester) > 0
        and run_patrol(self, ct)
    )


def _opportunistic_attack(self: Builder, ct: Controller) -> bool:
    if (
        self.opportunistic
        and self.rng.random() < 0.2
        and self.round > 100
        and ct.can_fire(self.my_pos)
        and ct.get_team(ct.get_tile_building_id(self.my_pos)) != self.my_team
    ):
        ct.fire(self.my_pos)
        return True
    return False


def _explore(self: Builder, ct: Controller) -> bool:
    if self.ti <= 100:
        return False
    explore(self, ct)
    return True


def _wander(self: Builder, ct: Controller) -> bool:
    dir8 = DIR8.copy()
    self.rng.shuffle(dir8)
    return any(try_move_dir(ct, d) for d in dir8) or any(
        try_move_with_road(self, ct, self.my_pos.add(d)) for d in dir8
    )


def _attack(s: Builder, ct: Controller) -> bool:
    run_attack(s, ct)
    return True


POLICIES: dict[Role, list[Callable[[Builder, Controller], bool]]] = {
    Role.OFFENSE: [
        _heal,
        deny_enemy_ore,
        _attack,
    ],
    Role.ECON: [
        place_gunner_nearby,
        fix_enemy_conveyor,
        pave_near_harvesters,
        _connect_close,
        _heal,
        deny_enemy_ore,
        _connect_far,
        _harvest,
        _opportunistic_attack,
        _explore,
        _wander,
    ],
    Role.DEFENSE: [
        place_gunner_nearby,
        fix_enemy_conveyor,
        pave_near_harvesters,
        _connect_close,
        _heal,
        deny_enemy_ore,
        _connect_far,
        _patrol_cheap,
        _harvest,
        _patrol_late,
        _opportunistic_attack,
        _explore,
        _wander,
    ],
}


class Builder(Unit):
    def update_pnb(self, i: int) -> None:
        w, h = self.w, self.h
        cost_grid = self.cost_grid
        pnb = self.pnb
        cx, cy = i % w, i // w
        passable = cost_grid[i] is not INF
        pnb[i] = []
        if passable:
            for dx, dy in DIR8_DELTA:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h:
                    ni = ny * w + nx
                    if cost_grid[ni] is not INF:
                        pnb[i].append(ni)
        for dx, dy in DIR8_DELTA:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                ni = ny * w + nx
                if cost_grid[ni] is INF:
                    continue
                nb_list = pnb[ni]
                if passable:
                    if i not in nb_list:
                        nb_list.append(i)
                elif i in nb_list:
                    nb_list.remove(i)

    def find_core(self, ct: Controller) -> Position:
        for bid in ct.get_nearby_buildings():
            if (
                ct.get_team(bid) == self.my_team
                and ct.get_entity_type(bid) == EntityType.CORE
            ):
                return ct.get_position(bid)
        msg = "Core not visible at spawn"
        raise RuntimeError(msg)

    @override
    def __init__(self, ct: Controller) -> None:
        super().__init__(ct)
        self.my_core: Final[Position] = self.find_core(ct)
        """Allied core. Always known, since builders always spawn inside the core."""
        w, h = self.w, self.h
        n: Final[int] = w * h

        self.env: list[Environment | None] = [None] * n
        """Wall, Empty, Ti ore, Ax ore per tile."""
        self.building_ids: list[int | None] = [None] * n
        """Cached building entity ID per tile, for change detection."""
        self.buildings: list[Building | None] = [None] * n
        """Building on a tile."""
        self.hp: list[int] = [0] * n
        """Hitpoints of building on tile."""
        self.max_hp: list[int] = [0] * n
        """Max hitpoints of building on tile."""

        self.cost_grid: list[int] = [1] * n
        """Movement cost per tile. INF = impassable, 1 = road/walkable, ROAD_COST = empty."""
        self.conveyor_cost_grid: list[int] = [5] * n
        """Conveyor routing cost per tile. Higher = less preferred."""

        offsets = [dy * w + dx for dx, dy in DIR8_DELTA]
        pnb: list[list[int]] = [[] for _ in range(n)]
        for cy in range(1, h - 1):
            row = cy * w
            for cx in range(1, w - 1):
                i = row + cx
                pnb[i] = [i + o for o in offsets]
        for cy in range(h):
            row = cy * w
            for cx in range(w):
                if 1 <= cx < w - 1 and 1 <= cy < h - 1:
                    continue
                i = row + cx
                pnb[i] = [
                    ny * w + nx
                    for dx, dy in DIR8_DELTA
                    if 0 <= (nx := cx + dx) < w and 0 <= (ny := cy + dy) < h
                ]
        self.pnb = pnb
        """Passable neighbours."""

        self.bfs_dist: Final[list[int]] = [INF] * n
        self.bfs_reset: Final[tuple[int, ...]] = (INF,) * n
        self.move_search: Final = MoveHeapAstar(self)
        self.conv_search: Final = AStarSearch(self)
        """BFS hops from the position at the start of the turn."""

        self.flow_history: list[deque[ResourceType | None]] = [
            deque([None] * 8, maxlen=8) for _ in range(n)
        ]
        """Last 8 rounds of resource flow on this tile."""

        self.conveyors_to_here: list[list[Position]] = [[] for _ in range(n)]
        self.splitters_to_here: list[list[Position]] = [[] for _ in range(n)]

        self.symmetry_candidates: set[Symmetry] = set(Symmetry)
        """The current set of symmetry hypotheses."""
        self.symmetry: Symmetry | None = None
        """If `symmetry == {x}`, then this is `x`, otherwise `None`."""

        self.reflect_queue: deque[int] = deque()
        """At the moment symmetry is known, existing tiles in memory have to be reflected.
        To prevent a huge spike, we process only a limited number per turn.
        """

        # Ephemeral (recomputed each turn)

        self.nearby_buildings: list[Position] = []
        self.healable_buildings: list[Position] = []
        self.adjacent_to_unconnected_harvester: set[Position] = set()
        self.adjacent_to_harvester: set[Position] = set()
        self.adjacent_to_enemy_launcher: set[Position] = set()

        self.enemy_turret_ray_tiles: set[Position] = set()
        """Tiles that are in the forward firing ray of an enemy gunner
        or sentinel. Populated per-turn in state_update_map when a
        visible enemy turret is encountered. Used as a soft cost
        penalty in cost_grid so move_search routes bots around them.
        """

        self.friendly_turret_ray_tiles: set[Position] = set()
        """Forward firing ray of FRIENDLY gunners/sentinels. Walking
        into one blocks our own shot for that turn — same soft
        penalty keeps bots off their own turrets' kill lanes.
        """

        self.deny_ore_neighbours: set[Position] = set()
        """Ore-denial tiles: for ores in our vision whose cardinal-8
        halo contains an enemy bot or building, the ore's 4 cardinal
        neighbours are candidate road-placement tiles. We pave them
        with cheap roads (1 Ti base) to deny the enemy a harvester
        feed position before they get one built.
        """

        self.nearest_enemy_turret: Position | None = None

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

        # Repair
        self.repair_pos: Position | None = None
        self.repaired_prev: bool = True

        # Offense
        self.en_core: bool = False
        self.offense_target: Position | None = None
        self.offense_turns: int = 0
        self.offense_launcher: Position | None = None

        self.last_fire: tuple[Position, int] | None = None
        """Track the tile we last fired at, plus the HP we expected to
        see on the building there NEXT turn (i.e. pre-fire HP minus
        our 2 dmg). If we revisit and the tile's current HP is
        higher than that expectation, an enemy builder healed it —
        concrete evidence we're being out-healed on this tile.
        """

        self.attack_tile_blacklist: dict[Position, int] = {}
        """Tiles we just got out-healed on: {tile: remaining_turns}.
        Decremented at the top of run_attack; _pick_attack_destination
        skips any entry still present. Stops the bounce loop where
        we rotate around the same harvester's neighbours turn after
        turn because the picker keeps picking one of a handful of
        valid tiles and a nearby enemy builder just heals us off it.
        """

        # Patrol
        self.patrol_head: Position | None = None
        self.patrol_trail: list[Position] = []

        # Scouting
        self.scout_target: Position | None = None
        self.scout_age: int = 0
        self.scout_radius: float = 10.0

    def get_env(self, pos: Position) -> Environment | None:
        return self.env[self.idx(pos)]

    def get_building(self, pos: Position) -> Building | None:
        return self.buildings[self.idx(pos)]

    def get_cost(self, pos: Position) -> int:
        return self.cost_grid[self.idx(pos)]

    def is_passable(self, pos: Position) -> bool:
        return self.cost_grid[self.idx(pos)] is not INF

    def is_walkable(self, pos: Position) -> bool:
        if not self.is_passable(pos):
            return False
        return isinstance(
            self.buildings[self.idx(pos)],
            BuildingConveyor
            | BuildingRoad
            | BuildingSplitter
            | BuildingArmouredConveyor
            | BuildingBridge,
        )

    def get_conveyors_to_here(self, pos: Position) -> list[Position]:
        return self.conveyors_to_here[self.idx(pos)]

    def is_buildable(self, pos: Position) -> bool:
        i = self.idx(pos)
        b = self.buildings[i]
        return self.env[i] != Environment.WALL and (b is None or b.team == self.my_team)

    def is_friendly_turret(self, pos: Position) -> bool:
        b = self.buildings[self.idx(pos)]
        if b is None or isinstance(
            b,
            BuildingConveyor
            | BuildingRoad
            | BuildingSplitter
            | BuildingArmouredConveyor
            | BuildingBridge,
        ):
            return False
        return b.team == self.my_team

    def is_enemy_building(self, pos: Position) -> bool:
        b = self.buildings[self.idx(pos)]
        return b is not None and b.team != self.my_team

    def leads_to_enemy_building(self, pos: Position) -> bool:
        b = self.buildings[self.idx(pos)]
        if b is None or b.team != self.my_team:
            return False
        match b:
            case BuildingConveyor(direction=d):
                output_location = pos.add(d)
            case BuildingBridge(target=t):
                output_location = t
            case _:
                return False
        if not self.in_bounds(output_location):
            return False
        return self.is_enemy_building(output_location)

    update = update
    prune_stale = prune_stale
    update_vision = update_vision
    update_bfs = update_bfs
    extract_path = extract_path
    update_ore_denial = update_ore_denial
    update_enemy_turrets = update_enemy_turrets
    update_role = update_role
    update_map_econ = update_map_econ
    update_dangling = update_dangling
    update_ore_target = update_ore_target
    can_place_junction = can_place_junction
    dump = dump

    @override
    def run(self, ct: Controller) -> None:
        super().run(ct)
        t0 = ct.get_cpu_time_elapsed()
        self.update(ct)

        if DEBUG_DUMP:
            self.dump(ct)

        t1 = ct.get_cpu_time_elapsed()
        chosen: str | None = None
        assert self.role is not None
        for task in POLICIES[self.role]:
            if task(self, ct):
                chosen = task.__name__
                break

        if self.role != Role.OFFENSE:
            self.end_of_turn_heal(ct)

        t2 = ct.get_cpu_time_elapsed()
        print(f"task={t2 - t1}us [{chosen}]")
        print(f"total={t2 - t0}us")

    def end_of_turn_heal(self, ct: Controller) -> None:
        my_pos = ct.get_position()
        if ct.can_heal(my_pos) and ct.get_hp() < ct.get_max_hp():
            ct.heal(my_pos)
        for unit in ct.get_nearby_units():
            if ct.get_team(unit) != self.my_team:
                continue
            if ct.get_hp(unit) >= ct.get_max_hp(unit):
                continue
            if ct.get_entity_type(unit) == EntityType.CORE:
                for d in DIR8:
                    heal_pos = ct.get_position(unit).add(d)
                    if ct.can_heal(heal_pos):
                        ct.heal(heal_pos)
                        break
            elif ct.can_heal(ct.get_position(unit)):
                ct.heal(ct.get_position(unit))
