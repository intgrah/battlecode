from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    Building,
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingCore,
    BuildingFoundry,
    BuildingGunner,
    BuildingHarvester,
    BuildingLauncher,
    BuildingMarker,
    BuildingRoad,
    BuildingSentinel,
    BuildingSplitter,
    make_building,
)
from cambc import Controller, EntityType, Environment, GameConstants
from util.constants import INF, MAX_WIDTH, ROAD_COST
from util.directions import DIR8, DIR4
from cambc import Position

if TYPE_CHECKING:
    from util.symmetry import Symmetry

    from builder import Builder


def _edge_targets(pos: Position, bld: Building) -> tuple[Position, ...]:
    """Structural output tiles of `bld` placed at `pos`. One entry for a
    conveyor / armoured conveyor / bridge; three for a splitter; empty for
    non-routing buildings (which participate via separate sets).
    """
    match bld:
        case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
            return (pos.add(d),)
        case BuildingBridge(target=t):
            return (t,)
        case BuildingSplitter(direction=d):
            return (
                pos.add(d),
                pos.add(d.rotate_right().rotate_right()),
                pos.add(d.rotate_left().rotate_left()),
            )
        case _:
            return ()


def _remove_topology(self: Builder, pos: Position, i: int) -> None:
    old_bld = self.buildings[i]
    if old_bld is not None and old_bld.team == self.my_team:
        for t in _edge_targets(pos, old_bld):
            if not self.in_bounds(t):
                continue
            ti = self.idx(t)
            if pos in self.in_edges[ti]:
                self.in_edges[ti].remove(pos)
                self._check_multi_input(t)
                self._check_dangling(t)
        self.out_edges[i] = []
    match old_bld:
        case BuildingFoundry(team=t) if t == self.my_team:
            self.my_foundries.discard(pos)
            self._bump_foundry(pos, -1)
        case BuildingHarvester():
            env = self.env[i]
            if env == Environment.ORE_AXIONITE:
                self._bump_ax_harv(pos, -1)
            elif env == Environment.ORE_TITANIUM:
                self._bump_ti_harv(pos, -1)


def _add_topology(self: Builder, pos: Position, bld: Building) -> None:
    if bld is not None and bld.team == self.my_team:
        targets = _edge_targets(pos, bld)
        if targets:
            outs: list[Position] = []
            for t in targets:
                if self.in_bounds(t):
                    self.in_edges[self.idx(t)].append(pos)
                    outs.append(t)
                    self._check_multi_input(t)
                    self._check_dangling(t)
            self.out_edges[pos.y * MAX_WIDTH + pos.x] = outs
            return
    match bld:
        case BuildingFoundry(team=self.my_team):
            self.my_foundries.add(pos)
            self._bump_foundry(pos, +1)
        case BuildingHarvester():
            match self.env[self.idx(pos)]:
                case Environment.ORE_AXIONITE:
                    self._bump_ax_harv(pos, +1)
                case Environment.ORE_TITANIUM:
                    self._bump_ti_harv(pos, +1)


def _update_cost(
    self: Builder,
    i: int,
    terrain: Environment | None,
    bld: Building | None,
) -> None:
    # Movement cost_grid: walkable tiles (roads, conveyors, splitters,
    # armoured conveyors, bridges, our core) are cheap; walls, ore tiles,
    # enemy buildings, and harvesters are impassable for movement.
    # buildable: True iff we can place a conveyor/bridge/etc. right now —
    # empty terrain with no building, OR friendly road, OR any marker
    # (1 HP, any team can overbuild).
    if terrain == Environment.WALL:
        cost = INF
        buildable = False
    elif bld is not None:
        match bld:
            case BuildingRoad(team=self.my_team):
                cost = 1
                buildable = True
            case BuildingMarker():
                cost = ROAD_COST
                buildable = True
            case (
                BuildingConveyor(team=t)
                | BuildingArmouredConveyor(team=t)
            ):
                cost = 1
                buildable = self.my_team == t and any(
                    isinstance(adjbld := self.get_building(j), BuildingHarvester) and adjbld.team == self.my_team for j in self.out_edges[i]
                )
            case (
                BuildingSplitter()
                | BuildingBridge()
            ):
                cost = 1
                buildable = False
            case BuildingCore(team=self.my_team):
                cost = 1
                buildable = False
            case BuildingHarvester(team=self.my_team):
                ipos = Position(i % MAX_WIDTH, i // MAX_WIDTH)
                for d in DIR4:
                    j = ipos.add(d)
                    if not self.in_bounds(j):
                        continue
                    ji = j.y * MAX_WIDTH + j.x
                    adjbld = self.buildings[ji]
                    if isinstance(adjbld, BuildingConveyor | BuildingArmouredConveyor) and adjbld.team == self.my_team:
                        if not self.buildable[ji]:
                            self.buildable[ji] = True
                            self.ti_routable[ji] = not self.ti_leakage[i]
                            self.ax_routable[ji] = not self.ax_leakage[i]
                cost = INF
                buildable = False
            case _:
                cost = INF
                buildable = False
    elif terrain == Environment.EMPTY:
        cost = ROAD_COST
        buildable = True
    else:  # ore tile with no building
        cost = ROAD_COST
        buildable = False
    self.cost_grid[i] = cost
    if self.buildable[i] != buildable:
        self.buildable[i] = buildable
        self.ti_routable[i] = buildable and not self.ti_leakage[i]
        self.ax_routable[i] = buildable and not self.ax_leakage[i]


def _update_turret_rays(
    self: Builder,
    ct: Controller,
    pos: Position,
    bld: Building,
) -> None:
    match bld:
        case BuildingLauncher(team=t) if t != self.my_team:
            for d in DIR8:
                n = pos.add(d)
                if self.in_bounds(n):
                    self.adjacent_to_enemy_launcher.add(n)
        case BuildingGunner(team=t, direction=d) if t != self.my_team:
            ray = pos
            for _ in range(3):
                ray = ray.add(d)
                if pos.distance_squared(ray) > GameConstants.GUNNER_VISION_RADIUS_SQ:
                    break
                if self.in_bounds(ray):
                    self.enemy_turret_ray_tiles.add(ray)
        case BuildingSentinel(team=t, direction=d) if t != self.my_team:
            for tile in ct.get_attackable_tiles_from(pos, d, EntityType.SENTINEL):
                self.enemy_turret_ray_tiles.add(tile)
        case BuildingGunner(team=t, direction=d) if t == self.my_team:
            ray = pos
            for _ in range(3):
                ray = ray.add(d)
                if pos.distance_squared(ray) > GameConstants.GUNNER_VISION_RADIUS_SQ:
                    break
                if not self.in_bounds(ray):
                    break
                if self.get_env(ray) == Environment.WALL:
                    break
                self.friendly_turret_ray_tiles.add(ray)
                if self.get_building(ray) is not None:
                    break
        case BuildingSentinel(team=t, direction=d) if t == self.my_team:
            ray = pos
            for _ in range(6):
                ray = ray.add(d)
                if pos.distance_squared(ray) > 32:
                    break
                if not self.in_bounds(ray):
                    break
                if self.get_env(ray) == Environment.WALL:
                    break
                self.friendly_turret_ray_tiles.add(ray)
                for hd in DIR8:
                    h = ray.add(hd)
                    if self.in_bounds(h):
                        self.friendly_turret_ray_tiles.add(h)
                if self.get_building(ray) is not None:
                    break


def update_vision(self: Builder, ct: Controller) -> None:
    new_observations: list[tuple[Position, Environment, bool]] = []
    for pos in self.nearby_tiles:
        i = self.idx(pos)
        env = ct.get_tile_env(pos)
        bid = ct.get_tile_building_id(pos)
        env_changed = self.env[i] != env
        bld_changed = self.building_ids[i] != bid
        if self.env[i] is None and env is not None:
            # First observation of this tile's env. Enqueue for later
            # symmetry reflection — queue drains only once self.symmetry
            # is resolved, but the enqueue is unconditional.
            self.reflect_queue.append(i)
            is_core = bid is not None and ct.get_entity_type(bid) == EntityType.CORE
            new_observations.append((pos, env, is_core))
        self.env[i] = env
        self.building_ids[i] = bid

        if bld_changed or env_changed:
            _remove_topology(self, pos, i)
            if bid is not None:
                bld = make_building(ct, bid, ct.get_entity_type(bid))
                self.buildings[i] = bld
                self.hp[i] = ct.get_hp(bid)
                self.max_hp[i] = ct.get_max_hp(bid)
                _add_topology(self, pos, bld)
            else:
                self.buildings[i] = None
                self.hp[i] = 0
                self.max_hp[i] = 0

            _update_cost(self, i, env, self.buildings[i])
            self.update_pnb(i)
            self._check_dangling(pos)
            # When pos transitions between consumer / non-consumer, the
            # satisfaction count of any splitter feeding pos changes, so
            # its OTHER outputs may flip dangling state.
            for feeder in self.in_edges[i]:
                fb = self.buildings[feeder.y * MAX_WIDTH + feeder.x]
                if isinstance(fb, BuildingSplitter):
                    for sib in self.out_edges[feeder.y * MAX_WIDTH + feeder.x]:
                        if sib != pos:
                            self._check_dangling(sib)
            bld = self.buildings[i]
            if bld is not None:
                _update_turret_rays(self, ct, pos, bld)
        else:
            bld = self.buildings[i]
            if bid is not None:
                self.hp[i] = ct.get_hp(bid)
                self.max_hp[i] = ct.get_max_hp(bid)

        if bid is not None:
            bld = self.buildings[i]
            self.nearby_buildings.append(pos)
            if (
                self.hp[i] < self.max_hp[i]
                and bld is not None
                and bld.team == self.my_team
            ):
                self.healable_buildings.append(pos)

            match bld:
                case (
                    BuildingConveyor()
                    | BuildingArmouredConveyor()
                    | BuildingBridge()
                    | BuildingSplitter()
                ):
                    # Bounded by FLOW_HISTORY_LEN; oldest entry is popped when full.
                    self.flow_history[i].append(
                        (ct.get_stored_resource(bid), ct.get_stored_resource_id(bid)),
                    )

    if self.symmetry is None:
        _narrow_symmetry(self, new_observations)


def _narrow_symmetry(
    self: Builder,
    new_observations: list[tuple[Position, Environment, bool]],
) -> None:
    """For each newly-observed tile, check each remaining symmetry
    candidate: if the mirror tile under that symmetry disagrees on env
    (or on whether it hosts a Core), the candidate is inconsistent and
    dropped. Once one candidate remains, promote to `self.symmetry`.
    """
    w, h = self.w, self.h
    invalid: set[Symmetry] = set()
    for sym in self.symmetry_candidates:
        for pos, env, is_core in new_observations:
            m = sym.action(pos, w, h)
            mi = m.y * MAX_WIDTH + m.x
            mirror_env = self.env[mi]
            if mirror_env is not None and mirror_env != env:
                invalid.add(sym)
                break
            mirror_bld = self.buildings[mi]
            mirror_is_core = isinstance(mirror_bld, BuildingCore)
            if mirror_env is not None and mirror_is_core != is_core:
                invalid.add(sym)
                break
    self.symmetry_candidates -= invalid
    if len(self.symmetry_candidates) == 1:
        self.symmetry = next(iter(self.symmetry_candidates))
