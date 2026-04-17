from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    ETYPE_BUILDING,
    Building,
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingCore,
    BuildingFoundry,
    BuildingGunner,
    BuildingHarvester,
    BuildingLauncher,
    BuildingRoad,
    BuildingSentinel,
    BuildingSplitter,
)
from cambc import Controller, EntityType, Environment, Position
from util import DIR4, DIR8, INF, Symmetry, DELTA_TO_DIR, DIR_TO_DELTA

if TYPE_CHECKING:
    from builder import Builder, PosInt

ROAD_COST = 3


def _make_building(self: Builder, ct: Controller, bid: int, etype: EntityType) -> Building | None:
    team = ct.get_team(bid)
    match etype:
        case EntityType.CONVEYOR | EntityType.ARMOURED_CONVEYOR | EntityType.SPLITTER:
            cls = ETYPE_BUILDING[etype]
            return cls(team, DIR_TO_DELTA[ct.get_direction(bid)])
        case EntityType.GUNNER | EntityType.SENTINEL | EntityType.BREACH:
            cls = ETYPE_BUILDING[etype]
            return cls(team, DIR_TO_DELTA[ct.get_direction(bid)])
        case EntityType.BRIDGE:
            return BuildingBridge(team, self._idx(ct.get_bridge_target(bid)))
        case _:
            cls = ETYPE_BUILDING.get(etype)
            if cls is None:
                return None
            return cls(team)


def load_penalty(load: int) -> int:
    # Integer-only so A*'s inner loop can index buckets without
    # casting — using 0/1/3/10/500 instead of 0/0.5/3.0/10.0/500.0.
    # The 0.5 rounded up to 1 loses almost no resolution and the
    # other values are already whole numbers.
    match load:
        case 0:
            return 0
        case 1:
            return 1
        case 2:
            return 3
        case 3:
            return 10
        case _:
            return 500


def can_place_junction(self: Builder, ct: Controller, i: PosInt) -> bool:
    match self.get_building(i):
        case None:
            pass
        case BuildingConveyor(team=t) | BuildingRoad(team=t) if t == self.my_team:
            pass
        case _:
            return False

    conveyors = self.get_conveyors_to_here(i)
    adjacent_conveyors = [c for c in conveyors if self.sq_dist(c, i) <= 2]
    if len(adjacent_conveyors) > 1 or len(conveyors) < 1:
        return False
    buildable_count = 0
    for d in DIR4:
        ni = i + d
        if self.get_env(ni) != Environment.EMPTY:
            continue
        match self.get_building(ni):
            case None:
                buildable_count += 1
            case BuildingConveyor() | BuildingBridge() | BuildingSplitter():
                pass
            case b if b.team == self.my_team:
                buildable_count += 1

    return buildable_count >= 1


def update_map(self: Builder, ct: Controller) -> None:
    w = self.w
    stride = self.dist_stride
    nearby_positions = [self._idx(p) for p in ct.get_nearby_tiles()]
    rnd = ct.get_current_round()
    self.nearby_positions = nearby_positions
    self.nearby_buildings = []

    in_vision = lambda x: ct.is_in_vision(self.pos(x))

    self.healable_buildings = [p for p in self.healable_buildings if not in_vision(p)]
    self.adjacent_to_enemy_launcher = {
        p for p in self.adjacent_to_enemy_launcher if not in_vision(p)
    }
    self.enemy_turret_ray_tiles = {
        p for p in self.enemy_turret_ray_tiles if not in_vision(p)
    }
    self.friendly_turret_ray_tiles = {
        p for p in self.friendly_turret_ray_tiles if not in_vision(p)
    }

    self.patrol_queue = [
        p for p in self.patrol_queue if not in_vision(p[0])
    ]

    for i in nearby_positions:
        self.conveyors_to_here[i] = [
            p for p in self.conveyors_to_here[i] if not in_vision(p)
        ]
        self.splitters_to_here[i] = [
            p for p in self.splitters_to_here[i] if not in_vision(p)
        ]

    pad = self.pad
    pw = self.pw
    my_team = self.my_team
    for i in nearby_positions:
        pos = self.pos(i)
        pi = (pos.y + pad) * pw + (pos.x + pad)

        tile_env = ct.get_tile_env(pos)
        self.env[i] = tile_env

        if tile_env == Environment.ORE_TITANIUM:
            self.ti_ore.add(i)
        elif tile_env == Environment.ORE_AXIONITE:
            self.ax_ore.add(i)

        building_id = ct.get_tile_building_id(pos)
        if (
            building_id is not None
            and ct.get_entity_type(building_id) != EntityType.MARKER
        ):
            etype = ct.get_entity_type(building_id)
            bld = _make_building(self, ct, building_id, etype)
            self.buildings[i] = bld
            self.hp[i] = ct.get_hp(building_id)
            self.max_hp[i] = ct.get_max_hp(building_id)


            match bld:
                case (
                    BuildingConveyor()
                    | BuildingArmouredConveyor()
                    | BuildingBridge()
                    | BuildingSplitter()
                    | BuildingFoundry()
                ):
                    rid = ct.get_stored_resource_id(building_id)
                    rtype = ct.get_stored_resource(building_id)
                    self.flow[i].update(rtype, rid)
            match bld:
                case BuildingConveyor(direction=d):
                    target_pos = i + d
                    if self.in_bounds(i):
                        self.conveyors_to_here[target_pos].append(i)
                case BuildingBridge(target=t):
                    if self.in_bounds(t):
                        self.conveyors_to_here[t].append(i)
                case BuildingSplitter(direction=d):
                    for sd in [
                        d,
                        DIR_TO_DELTA[DELTA_TO_DIR[d].rotate_right().rotate_right()],
                        DIR_TO_DELTA[DELTA_TO_DIR[d].rotate_left().rotate_left()],
                    ]:
                        target_pos = i + sd
                        if self.in_bounds(target_pos):
                            self.splitters_to_here[target_pos].append(i)

            self.nearby_buildings.append(i)
            if (
                self.hp[i] < self.max_hp[i]
                and bld is not None
                and bld.team == self.my_team
            ):
                self.healable_buildings.append(i)
            match bld:
                case BuildingLauncher(team=t) if t != self.my_team:
                    for d in DIR8:
                        n = i + d
                        if self.in_bounds(n):
                            self.adjacent_to_enemy_launcher.add(n)
                case BuildingGunner(team=t, direction=d) if t != self.my_team:
                    # Gunner forward ray: up to r²≤13 (3 cardinal
                    # or ~2.5 diagonal steps). Each tile along the
                    # ray is a soft-penalty zone for movement.
                    ray = i
                    for _ in range(4):
                        ray = ray + d
                        if self.sq_dist(i, ray) > 13:
                            break
                        if self.in_bounds(ray):
                            self.enemy_turret_ray_tiles.add(ray)
                case BuildingSentinel(team=t, direction=d) if t != self.my_team:
                    # Sentinel: forward line plus 1 king-move
                    # halo, up to r²≤32. Add the core line and
                    # its 8-neighbour halo for each step.
                    ray = i
                    for _ in range(6):
                        ray = ray + d
                        if self.sq_dist(i, ray) > 32:
                            break
                        if self.in_bounds(ray):
                            self.enemy_turret_ray_tiles.add(ray)
                        for hd in DIR8:
                            h = ray + hd
                            if self.in_bounds(h):
                                self.enemy_turret_ray_tiles.add(h)
                case BuildingGunner(team=t, direction=d) if t == self.my_team:
                    # Friendly gunner ray — walk forward, add tiles
                    # up to r²≤13, stop at the first wall or any
                    # building (friendly or enemy). Past that tile
                    # the gunner can't hit anything anyway, so we
                    # don't need to warn bots off tiles past it.
                    # Read from state cache (not `ct.*` methods):
                    # ray tiles can extend past our bot's vision
                    # when the gunner is near the edge, and the
                    # controller raises on out-of-vision queries.
                    ray = i
                    for _ in range(4):
                        ray = ray + d
                        if self.sq_dist(i, ray) > 13:
                            break
                        if not self.in_bounds(ray):
                            break
                        if self.get_env(ray) == Environment.WALL:
                            break
                        self.friendly_turret_ray_tiles.add(ray)
                        if self.get_building(ray) is not None:
                            break
                case BuildingSentinel(team=t, direction=d) if t == self.my_team:
                    # Friendly sentinel ray — core line + 1-king
                    # halo, up to r²≤32, again stopping at the
                    # first building in the core line. Same
                    # vision-safety reasoning as the gunner case.
                    ray = i
                    for _ in range(6):
                        ray = ray + d
                        if self.sq_dist(i, ray) > 32:
                            break
                        if not self.in_bounds(ray):
                            break
                        if self.get_env(ray) == Environment.WALL:
                            break
                        self.friendly_turret_ray_tiles.add(ray)
                        for hd in DIR8:
                            h = ray + hd
                            if self.in_bounds(h):
                                self.friendly_turret_ray_tiles.add(h)
                        if self.get_building(ray) is not None:
                            break
        else:
            self.buildings[i] = None

        # update conveyor cost grid
        terrain = self.env[i]
        bld = self.buildings[i]
        if terrain == Environment.WALL:
            conveyor_cost = INF
        elif bld is not None:
            match bld:
                case BuildingRoad():
                    conveyor_cost = 1
                case (
                    BuildingConveyor(team=t) 
                    | BuildingArmouredConveyor(team=t) 
                    | BuildingSplitter(team=t) 
                    | BuildingBridge(team=t)
                ):
                    if t == my_team:
                        conveyor_cost = 1
                    else:
                        conveyor_cost = 1 if self.has_flow(i) else 10
                case BuildingCore(team=t) if t == self.my_team:
                    conveyor_cost = 1
                case _:
                    conveyor_cost = INF
        elif terrain == Environment.EMPTY:
            conveyor_cost = 1
        else:
            conveyor_cost = 10

        pi = (pos.y + pad) * pw + (pos.x + pad)
        self.conveyor_cost_grid[pi] = conveyor_cost
        assert self.conveyor_cost_grid[pi] > 0

    # update pass grid (pass_grid uses stride-w real indices internally)
    for pos in nearby_positions:
        bid = ct.get_tile_building_id(self.pos(pos))
        self.pass_grid.update_tile(
            self.pos(pos),
            self.env[pos],
            EntityType.LAUNCHER if pos in self.adjacent_to_enemy_launcher else None if bid is None else ct.get_entity_type(bid),
            is_allied_building=(bid is not None and ct.get_team(bid) == my_team),
        )

    my_pos = self.my_pos

    for pos in nearby_positions:
        core_bonus = max(0, 100 - self.sq_dist(self.my_core, pos)) / 100 * 0.25
        b = self.get_building(pos)
        if isinstance(b, (BuildingHarvester, BuildingFoundry)) and b.team == my_team:
            self.patrol_queue.append((pos, rnd, 1 + core_bonus))
        elif self.has_flow(pos):
            flow = self.get_flow(pos)
            ti_bonus = flow.ti / 4 * 0.25
            ax_bonus = flow.ax / 4 * 0.15
            rax_bonus = flow.rax / 4 * 0.35
            self.patrol_queue.append((pos, rnd, 0.5 + ti_bonus + ax_bonus + rax_bonus + core_bonus))

    # Ore-denial set: rebuilt each turn (cheap, bounded by vision).
    # For each ore tile in vision with any enemy bot/building in its
    # cardinal-8 halo, mark the ore's 4 cardinal neighbours as
    # denial-road candidates.
    self.deny_ore_neighbours = set()
    my_team = self.my_team
    for pos in nearby_positions:
        if not self.in_bounds(pos):
            continue
        env = self.env[pos]
        if env not in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE):
            continue
        has_enemy = False
        for d in DIR8:
            n = pos + d
            if not self.in_bounds(n):
                continue
            nb = self.buildings[n]
            if nb is not None and nb.team != my_team:
                has_enemy = True
                break
            if ct.is_in_vision(self.pos(n)):
                uid = ct.get_tile_builder_bot_id(self.pos(n))
                if uid is not None and ct.get_team(uid) != my_team:
                    has_enemy = True
                    break
        if has_enemy:
            for d in DIR4:
                n = pos + d
                if self.in_bounds(n):
                    self.deny_ore_neighbours.add(n)

        if self.nearest_enemy_turret:
            match self.buildings[pos]:
                case BuildingGunner(team=t) | BuildingSentinel(team=t) if (
                    t != self.my_team
                ):
                    pass
                case _:
                    self.nearest_enemy_turret = None
        min_dist = INF
        for pos in nearby_positions:
            match self.buildings[pos]:
                case BuildingGunner(team=t) | BuildingSentinel(team=t) if (
                    t != self.my_team
                ):
                    dist = self.sq_dist(pos, my_pos)
                    if dist < min_dist:
                        min_dist = dist
                        self.nearest_enemy_turret = pos


def update_splittable_locations(self: Builder, ct: Controller) -> None:
    pad = self.pad
    pw = self.pw
    self.adjacent_to_unconnected_harvester = {
        p for p in self.adjacent_to_unconnected_harvester if not ct.is_in_vision(self.pos(p))
    }
    self.adjacent_to_harvester = {
        p for p in self.adjacent_to_harvester if not ct.is_in_vision(self.pos(p))
    }
    for i in self.nearby_positions:
        pos = self.pos(i)
        pi = (pos.y + pad) * pw + (pos.x + pad)
        bld = self.get_building(self._idx(pos))
        match bld:
            case BuildingHarvester():
                adjacent_conveyor = False
                for dir in DIR4:
                    match self.get_building(i + dir):
                        case (
                            BuildingConveyor(team=t, direction=d)
                            | BuildingSplitter(team=t, direction=d)
                            | BuildingArmouredConveyor(team=t, direction=d)
                        ) if t == self.my_team and d != -dir:
                            adjacent_conveyor = True
                            break
                        case BuildingBridge(team=t) if t == self.my_team:
                            adjacent_conveyor = True
                            break
                if not adjacent_conveyor:
                    for dir in DIR4:
                        n = i + dir
                        if self.in_bounds(n):
                            self.adjacent_to_unconnected_harvester.add(n)
                for dir in DIR4:
                    n = i + dir
                    if self.in_bounds(n):
                        self.adjacent_to_harvester.add(n)

        # match bld:
        #    case (
        #        BuildingConveyor(team=t)
        #        | BuildingArmouredConveyor(team=t)
        #        | BuildingSplitter(team=t)
        #        | BuildingBridge(team=t)
        #    ) if t == self.my_team:
        #        self.conveyor_cost_grid[pi] += load_penalty(
        #            self.update_line_load_counts(pos)
        #        )

    if self.nearest_junction_site and not can_place_junction(
        self, ct, self.nearest_junction_site
    ):
        self.nearest_junction_site = None
    for pos in self.nearby_positions:
        if (
            self.nearest_junction_site is None
            or (
                self.my_sq_dist(self.nearest_junction_site)
                < self.my_sq_dist(pos)
            )
        ) and can_place_junction(self, ct, pos):
            self.nearest_junction_site = pos

_REFLECT_BUDGET = 25


def _mirror(self: Builder, pos: Position) -> Position:
    match self.symmetry:
        case Symmetry.ROT:
            return Position(self.w - 1 - pos.x, self.h - 1 - pos.y)
        case Symmetry.HOR:
            return Position(pos.x, self.h - 1 - pos.y)
        case Symmetry.VER:
            return Position(self.w - 1 - pos.x, pos.y)
        case None:
            return pos


def _set_enemy_core(self: Builder) -> None:
    pass


def _apply_symmetry(
    self: Builder,
    new_tiles: list[tuple[Position, Environment]],
) -> None:
    had_symmetry = self.symmetry is not None
    if not had_symmetry:
        _eliminate_symmetries(self, new_tiles)
    if self.symmetry is None:
        return
    stride = self.dist_stride
    if had_symmetry:
        source = new_tiles
    else:
        _set_enemy_core(self)
        # `e is not None` skips holes (x in [w, 2w)) since they're
        # never written, as well as unseen valid tiles.
        source = [
            (Position(i % stride, i // stride), e)
            for i, e in enumerate(self.env)
            if e is not None
        ]
    pending = self.reflect_queue
    for t, env in source:
        m = _mirror(self, t)
        mi = m.y * stride + m.x
        if self.env[mi] is not None:
            continue
        self.env[mi] = env
        pending.append(mi)


def _drain_reflect_queue(self: Builder) -> None:
    pending = self.reflect_queue
    if not pending:
        return
    stride = self.dist_stride
    pad = self.pad
    pw = self.pw
    limit = min(len(pending), _REFLECT_BUDGET)
    for _ in range(limit):
        i = pending.popleft()
        terrain = self.env[i]
        pi = ((i // stride) + pad) * pw + ((i % stride) + pad)
        if terrain == Environment.WALL:
            self.conveyor_cost_grid[pi] = INF
        elif terrain in (
            Environment.EMPTY,
            Environment.ORE_TITANIUM,
            Environment.ORE_AXIONITE,
        ):
            self.conveyor_cost_grid[pi] = 1 if terrain == Environment.EMPTY else 10


def _eliminate_symmetries(
    self: Builder, new_tiles: list[tuple[Position, Environment]]
) -> None:
    if not self.symmetry_candidates:
        return

    w, h = self.w, self.h
    stride = self.dist_stride
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

            mirror_env = self.env[sy * stride + sx]
            if mirror_env is not None and mirror_env != env:
                invalid.add(sym)
                break

            b1 = self.buildings[pos.y * stride + pos.x]
            b2 = self.buildings[sy * stride + sx]
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

    if self.symmetry is None and len(self.symmetry_candidates) is 1:
        self.symmetry = next(iter(self.symmetry_candidates))
