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
from cambc import Controller, EntityType, Environment, Position
from config import DEBUG_DUMP
from unit import Unit
from util import DIR8, DIR8_DELTA, INF, Symmetry, can_afford, try_move

from builder.algorithms.bfs import extract_path, update_bfs
from builder.dump import dump
from builder.extra import deny_enemy_ore, fix_enemy_conveyor, pave_near_harvesters
from builder.helpers import try_move_with_road
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
        and not can_afford(ct, EntityType.HARVESTER)
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
        and ct.get_current_round() > 100
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
    dir8 = DIR8.copy()
    self.rng.shuffle(dir8)
    return any(try_move(ct, self.my_pos.add(d)) for d in dir8) or any(
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
        pw = self.pad_w
        pad = self.pad
        cost_grid = self.cost_grid
        pnb = self.pnb
        cx, cy = i % w, i // w
        pi = (cy + pad) * pw + (cx + pad)
        passable = cost_grid[pi] < INF
        pnb[i] = []
        if passable:
            for dx, dy in DIR8_DELTA:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h:
                    ni = ny * w + nx
                    npi = (ny + pad) * pw + (nx + pad)
                    if cost_grid[npi] < INF:
                        pnb[i].append(ni)
        for dx, dy in DIR8_DELTA:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                ni = ny * w + nx
                npi = (ny + pad) * pw + (nx + pad)
                if cost_grid[npi] >= INF:
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

        # Padded cost-grid dimensions. A 3-tile border on every side
        # gives A* unconditional neighbor lookups for the bridge
        # r²≤9 set — any out-of-bounds neighbor lands on the padding
        # which is permanently INF, so the inner loop drops bounds
        # checks entirely. Only `cost_grid` and `conveyor_cost_grid`
        # use the padded layout; env/buildings/hp/... stay real-sized.
        self.pad: Final[int] = 3
        self.pad_w: Final[int] = w + 2 * self.pad
        self.pad_h: Final[int] = h + 2 * self.pad
        pad_n: Final[int] = self.pad_w * self.pad_h

        self.env: list[Environment | None] = [None] * n
        """Wall, Empty, Ti ore, Ax ore per tile."""
        self.buildings: list[Building | None] = [None] * n
        """Building on a tile."""
        self.hp: list[int] = [0] * n
        """Hitpoints of building on tile."""
        self.max_hp: list[int] = [0] * n
        """Max hitpoints of building on tile."""

        # Padded cost grids: border = INF, interior initialised to
        # the default cost for an unseen tile. Real tile (x, y) lives
        # at padded index (y + pad) * pw + (x + pad).
        self.cost_grid: list[int] = [INF] * pad_n
        self.conveyor_cost_grid: list[int] = [INF] * pad_n
        self._init_pad_interior()
        self.pnb: list[list[int]] = [
            [
                ny * w + nx
                for dx, dy in DIR8_DELTA
                if self.in_bounds(Position(nx := cx + dx, ny := cy + dy))
            ]
            for cy in range(h)
            for cx in range(w)
        ]
        """Passable neighbours."""

        self.bfs_dist: Final[list[int]] = [INF] * n
        """BFS hops from the position at the start of the turn."""

        self.flow_history: list[int] = [0b0000000000000000] * n
        """History of flow on this tile, encoded as a 8 entries * 2 bit = 16 bit queue.
        None = 0, Ti = 1, Raw Ax = 2, Refined Ax = 3.
        """

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
        self.nearby_positions: list[Position] = []
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

    def _init_pad_interior(self) -> None:
        """Seed interior cells of the padded cost grids. The border
        was already filled with INF by the constructor.
        """
        pad = self.pad
        pw = self.pad_w
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

    def _pidx(self, pos: Position) -> int:
        """Padded flat index for cost_grid / conveyor_cost_grid."""
        return (pos.y + self.pad) * self.pad_w + (pos.x + self.pad)

    def get_env(self, pos: Position) -> Environment | None:
        if self.in_bounds(pos):
            return self.env[self.idx(pos)]
        return None

    def get_building(self, pos: Position) -> Building | None:
        if self.in_bounds(pos):
            return self.buildings[self.idx(pos)]
        return None

    def get_cost(self, pos: Position) -> int:
        if self.in_bounds(pos):
            return self.cost_grid[self._pidx(pos)]
        return INF

    def is_passable(self, pos: Position) -> bool | None:
        return self.get_cost(pos) < INF

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
            return self.conveyors_to_here[self.idx(pos)]
        return []

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
        match self.buildings[self.idx(pos)]:
            case (
                None
                | BuildingConveyor()
                | BuildingRoad()
                | BuildingSplitter()
                | BuildingArmouredConveyor()
                | BuildingBridge()
            ):
                return False
            case b:
                return b.team == self.my_team

    def is_enemy_building(self, pos: Position) -> bool:
        if self.in_bounds(pos):
            b = self.buildings[self.idx(pos)]
            return b is not None and b.team != self.my_team
        return False

    def leads_to_enemy_building(self, pos: Position) -> bool:
        if self.in_bounds(pos):
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
            return self.is_enemy_building(output_location)
        return False

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
        nearby_units = [
            unit
            for unit in ct.get_nearby_units()
            if (ct.get_position(unit).distance_squared(my_pos) <= 2)
            or (ct.get_entity_type(unit) == EntityType.CORE)
        ]
        if ct.can_heal(my_pos) and ct.get_hp() < ct.get_max_hp():
            ct.heal(my_pos)
        for unit in nearby_units:
            if ct.get_entity_type(unit) == EntityType.CORE:
                core_center = ct.get_position(unit)
                for d in DIR8:
                    heal_pos = core_center.add(d)
                    if (
                        ct.can_heal(heal_pos)
                        and ct.get_team(unit) == self.my_team
                        and ct.get_hp(unit) < ct.get_max_hp(unit)
                    ):
                        ct.heal(heal_pos)

            if (
                ct.can_heal(ct.get_position(unit))
                and ct.get_team(unit) == self.my_team
                and ct.get_hp(unit) < ct.get_max_hp(unit)
            ):
                ct.heal(ct.get_position(unit))
