from __future__ import annotations

from typing import TYPE_CHECKING

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
from cambc import Controller, EntityType, Environment, GameConstants, Position
from util import DIR4, DIR8, INF, Symmetry

if TYPE_CHECKING:
    from .state import State

ROAD_COST = 3


def _make_building(ct: Controller, bid: int, etype: EntityType) -> Building | None:
    team = ct.get_team(bid)
    match etype:
        case EntityType.CONVEYOR | EntityType.ARMOURED_CONVEYOR | EntityType.SPLITTER:
            cls = ETYPE_BUILDING[etype]
            return cls(team, ct.get_direction(bid))
        case EntityType.GUNNER | EntityType.SENTINEL | EntityType.BREACH:
            cls = ETYPE_BUILDING[etype]
            return cls(team, ct.get_direction(bid))
        case EntityType.BRIDGE:
            return BuildingBridge(team, ct.get_bridge_target(bid))
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


def can_place_junction(state: State, ct: Controller, pos: Position) -> bool:
    match state.get_building(pos):
        case None:
            pass
        case BuildingConveyor(team=t) | BuildingRoad(team=t) if t == ct.get_team():
            pass
        case _:
            return False

    conveyors = state.get_conveyors_to_here(pos)
    adjacent_conveyors = [c for c in conveyors if c.distance_squared(pos) <= 2]
    if len(adjacent_conveyors) > 1 or len(conveyors) < 1:
        return False
    buildable_count = 0
    for d in DIR4:
        new_pos = pos.add(d)
        if state.get_env(new_pos) != Environment.EMPTY:
            continue
        match state.get_building(new_pos):
            case None:
                buildable_count += 1
            case BuildingConveyor() | BuildingBridge() | BuildingSplitter():
                pass
            case b if b.team == ct.get_team():
                buildable_count += 1

    return buildable_count >= 1


def update_map(state: State, ct: Controller) -> None:
    w = state.w
    nearby_positions = ct.get_nearby_tiles(GameConstants.BUILDER_BOT_VISION_RADIUS_SQ)
    state.nearby_positions = nearby_positions
    state.nearby_buildings = []

    state.healable_buildings = [
        p for p in state.healable_buildings if not ct.is_in_vision(p)
    ]
    state.adjacent_to_enemy_launcher = {
        p for p in state.adjacent_to_enemy_launcher if not ct.is_in_vision(p)
    }
    state.enemy_turret_ray_tiles = {
        p for p in state.enemy_turret_ray_tiles if not ct.is_in_vision(p)
    }

    for pos in nearby_positions:
        if 0 <= pos.x < state.w and 0 <= pos.y < state.h:
            i = pos.y * w + pos.x
            state.conveyors_to_here[i] = [
                p for p in state.conveyors_to_here[i] if not ct.is_in_vision(p)
            ]
            state.splitters_to_here[i] = [
                p for p in state.splitters_to_here[i] if not ct.is_in_vision(p)
            ]

    pad = state.pad
    pw = state.pw
    my_team = ct.get_team()
    pass_grid = state.pass_grid
    for pos in nearby_positions:
        if 0 <= pos.x < state.w and 0 <= pos.y < state.h:
            i = pos.y * w + pos.x
            pi = (pos.y + pad) * pw + (pos.x + pad)
            state.env[i] = ct.get_tile_env(pos)
            building_id = ct.get_tile_building_id(pos)
            if (
                building_id is not None
                and ct.get_entity_type(building_id) != EntityType.MARKER
            ):
                etype = ct.get_entity_type(building_id)
                bld = _make_building(ct, building_id, etype)
                state.buildings[i] = bld
                state.hp[i] = ct.get_hp(building_id)
                state.max_hp[i] = ct.get_max_hp(building_id)
                # Feed adgato PassableGrid with the real observed tile.
                pass_grid.update_tile(
                    i,
                    state.env[i],
                    etype,
                    is_allied_building=ct.get_team(building_id) == my_team,
                )

                match bld:
                    case BuildingConveyor() | BuildingBridge():
                        if ct.get_stored_resource(building_id) is not None:
                            state.belt_load_counts[i] += 1
                        else:
                            state.belt_load_counts[i] = 0
                    case BuildingSplitter():
                        state.belt_load_counts[i] = 100

                match bld:
                    case BuildingConveyor(direction=d):
                        target_pos = pos.add(d)
                        if 0 <= target_pos.x < state.w and 0 <= target_pos.y < state.h:
                            ti = target_pos.y * w + target_pos.x
                            state.conveyors_to_here[ti].append(pos)
                    case BuildingBridge(target=t):
                        if 0 <= t.x < state.w and 0 <= t.y < state.h:
                            ti = t.y * w + t.x
                            state.conveyors_to_here[ti].append(pos)
                    case BuildingSplitter(direction=d):
                        for sd in [
                            d,
                            d.rotate_right().rotate_right(),
                            d.rotate_left().rotate_left(),
                        ]:
                            target_pos = pos.add(sd)
                            if (
                                0 <= target_pos.x < state.w
                                and 0 <= target_pos.y < state.h
                            ):
                                ti = target_pos.y * w + target_pos.x
                                state.splitters_to_here[ti].append(pos)

                state.nearby_buildings.append(pos)
                if (
                    state.hp[i] < state.max_hp[i]
                    and bld is not None
                    and bld.team == ct.get_team()
                ):
                    state.healable_buildings.append(pos)
                match bld:
                    case BuildingLauncher(team=t) if t != ct.get_team():
                        for d in DIR8:
                            n = pos.add(d)
                            if 0 <= n.x < state.w and 0 <= n.y < state.h:
                                state.adjacent_to_enemy_launcher.add(n)
                    case BuildingGunner(team=t, direction=d) if (
                        t != ct.get_team()
                    ):
                        # Gunner forward ray: up to r²≤13 (3 cardinal
                        # or ~2.5 diagonal steps). Each tile along the
                        # ray is a soft-penalty zone for movement.
                        ray = pos
                        for _ in range(4):
                            ray = ray.add(d)
                            if pos.distance_squared(ray) > 13:
                                break
                            if 0 <= ray.x < state.w and 0 <= ray.y < state.h:
                                state.enemy_turret_ray_tiles.add(ray)
                    case BuildingSentinel(team=t, direction=d) if (
                        t != ct.get_team()
                    ):
                        # Sentinel: forward line plus 1 king-move
                        # halo, up to r²≤32. Add the core line and
                        # its 8-neighbour halo for each step.
                        ray = pos
                        for _ in range(6):
                            ray = ray.add(d)
                            if pos.distance_squared(ray) > 32:
                                break
                            if 0 <= ray.x < state.w and 0 <= ray.y < state.h:
                                state.enemy_turret_ray_tiles.add(ray)
                            for hd in DIR8:
                                h = ray.add(hd)
                                if 0 <= h.x < state.w and 0 <= h.y < state.h:
                                    state.enemy_turret_ray_tiles.add(h)
            else:
                state.buildings[i] = None
                # Marker or empty tile: let pass_grid decide based
                # on terrain alone (walls impassable, rest walkable).
                pass_grid.update_tile(
                    i,
                    state.env[i],
                    None,
                    is_allied_building=False,
                )

            terrain = state.env[i]
            bld = state.buildings[i]
            if terrain == Environment.WALL:
                cost = INF
                conveyor_cost = INF
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
                        conveyor_cost = INF
            elif terrain in (
                Environment.EMPTY,
                Environment.ORE_TITANIUM,
                Environment.ORE_AXIONITE,
            ):
                cost = ROAD_COST
                # Ore tiles cost 10 (vs 1 for empty): strongly prefer
                # non-ore routes but still permit chains to cross ore
                # when needed. Was 50 which over-penalized and blew
                # up Dial's bucket budget (max edge = 50 + bridge 7 +
                # h_diff 3 = 60). With 10 we cap max edge at ~20.
                conveyor_cost = 1 if terrain == Environment.EMPTY else 10
            else:
                cost = 1
                conveyor_cost = 1
            state.cost_grid[pi] = cost
            state.line_loads_computed[i] = False
            state.conveyor_cost_grid[pi] = conveyor_cost

    # new_tiles: list[tuple[Position, Environment]] = []
    # for pos in nearby_positions:
    #     if 0 <= pos.x < state.w and 0 <= pos.y < state.h:
    #         e = state.env[pos.y * w + pos.x]
    #         if e is not None:
    #             new_tiles.append((pos, e))
    # _apply_symmetry(state, new_tiles)
    # _drain_reflect_queue(state)

    my_pos = ct.get_position()
    for pos in nearby_positions:
        if (
            state.env[pos.y * w + pos.x]
            in [Environment.ORE_TITANIUM, Environment.ORE_AXIONITE]
            and state.buildings[pos.y * w + pos.x] is None
        ):
            pass

    if state.nearest_enemy_turret:
        match state.buildings[pos.y * w + pos.x]:
            case BuildingGunner(team=t) | BuildingSentinel(team=t) if (
                t != ct.get_team()
            ):
                pass
            case _:
                state.nearest_enemy_turret = None
    min_dist = INF
    for pos in nearby_positions:
        match state.buildings[pos.y * w + pos.x]:
            case BuildingGunner(team=t) | BuildingSentinel(team=t) if (
                t != ct.get_team()
            ):
                dist = (pos.x - my_pos.x) ** 2 + (pos.y - my_pos.y) ** 2
                if dist < min_dist:
                    min_dist = dist
                    state.nearest_enemy_turret = pos


def update_splittable_locations(state: State, ct: Controller) -> None:
    pad = state.pad
    pw = state.pw
    state.adjacent_to_unconnected_harvester = {
        p for p in state.adjacent_to_unconnected_harvester if not ct.is_in_vision(p)
    }
    state.adjacent_to_harvester = {
        p for p in state.adjacent_to_harvester if not ct.is_in_vision(p)
    }
    for pos in state.nearby_positions:
        pi = (pos.y + pad) * pw + (pos.x + pad)
        bld = state.get_building(pos)
        match bld:
            case BuildingHarvester():
                adjacent_conveyor = False
                for d in DIR4:
                    match state.get_building(pos.add(d)):
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
                        n = pos.add(d)
                        if 0 <= n.x < state.w and 0 <= n.y < state.h:
                            state.adjacent_to_unconnected_harvester.add(n)
                for d in DIR4:
                    n = pos.add(d)
                    if 0 <= n.x < state.w and 0 <= n.y < state.h:
                        state.adjacent_to_harvester.add(n)
        if pos in state.adjacent_to_enemy_launcher:
            state.cost_grid[pi] += 20
        if pos in state.enemy_turret_ray_tiles:
            # Soft penalty: bots route around enemy gunner/sentinel
            # firing lines when the detour is cheap. Not hard
            # impassable because sometimes we have to walk through
            # one (e.g. healing a tile on the other side, or closing
            # in on the turret itself). +15 makes ~5 tiles of detour
            # a break-even.
            state.cost_grid[pi] += 15

        match bld:
            case (
                BuildingConveyor(team=t)
                | BuildingArmouredConveyor(team=t)
                | BuildingSplitter(team=t)
                | BuildingBridge(team=t)
            ) if t == ct.get_team():
                state.conveyor_cost_grid[pi] += load_penalty(
                    state.update_line_load_counts(pos)
                )

    my_position = ct.get_position()
    if state.nearest_junction_site and not can_place_junction(
        state, ct, state.nearest_junction_site
    ):
        state.nearest_junction_site = None
    for pos in state.nearby_positions:
        if (
            state.nearest_junction_site is None
            or (
                state.nearest_junction_site.distance_squared(my_position)
                < pos.distance_squared(my_position)
            )
        ) and can_place_junction(state, ct, pos):
            state.nearest_junction_site = pos


_REFLECT_BUDGET = 25


def _mirror(state: State, pos: Position) -> Position:
    match state.symmetry:
        case Symmetry.ROT:
            return Position(state.w - 1 - pos.x, state.h - 1 - pos.y)
        case Symmetry.HOR:
            return Position(pos.x, state.h - 1 - pos.y)
        case Symmetry.VER:
            return Position(state.w - 1 - pos.x, pos.y)
        case None:
            return pos


def _set_enemy_core(state: State) -> None:
    core = _mirror(state, state.my_core)
    pad = state.pad
    pw = state.pw
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            cx, cy = core.x + dx, core.y + dy
            if 0 <= cx < state.w and 0 <= cy < state.h:
                state.cost_grid[(cy + pad) * pw + (cx + pad)] = INF


def _apply_symmetry(
    state: State,
    new_tiles: list[tuple[Position, Environment]],
) -> None:
    had_symmetry = state.symmetry is not None
    if not had_symmetry:
        _eliminate_symmetries(state, new_tiles)
    if state.symmetry is None:
        return
    w = state.w
    if had_symmetry:
        source = new_tiles
    else:
        _set_enemy_core(state)
        source = [
            (Position(i % w, i // w), e)
            for i, e in enumerate(state.env)
            if e is not None
        ]
    pending = state.reflect_queue
    for t, env in source:
        m = _mirror(state, t)
        mi = m.y * w + m.x
        if state.env[mi] is not None:
            continue
        state.env[mi] = env
        pending.append(mi)


def _drain_reflect_queue(state: State) -> None:
    pending = state.reflect_queue
    if not pending:
        return
    w = state.w
    pad = state.pad
    pw = state.pw
    limit = min(len(pending), _REFLECT_BUDGET)
    for _ in range(limit):
        i = pending.popleft()
        terrain = state.env[i]
        pi = ((i // w) + pad) * pw + ((i % w) + pad)
        if terrain == Environment.WALL:
            state.cost_grid[pi] = INF
            state.conveyor_cost_grid[pi] = INF
        elif terrain in (
            Environment.EMPTY,
            Environment.ORE_TITANIUM,
            Environment.ORE_AXIONITE,
        ):
            state.cost_grid[pi] = ROAD_COST
            state.conveyor_cost_grid[pi] = 1 if terrain == Environment.EMPTY else 10


def _eliminate_symmetries(
    state: State, new_tiles: list[tuple[Position, Environment]]
) -> None:
    if not state.symmetry_candidates:
        return

    w, h = state.w, state.h
    invalid: set[Symmetry] = set()

    for sym in state.symmetry_candidates:
        for pos, env in new_tiles:
            match sym:
                case Symmetry.HOR:
                    sx, sy = pos.x, h - 1 - pos.y
                case Symmetry.VER:
                    sx, sy = w - 1 - pos.x, pos.y
                case Symmetry.ROT:
                    sx, sy = w - 1 - pos.x, h - 1 - pos.y

            mirror_env = state.env[sy * w + sx]
            if mirror_env is not None and mirror_env != env:
                invalid.add(sym)
                break

            b1 = state.buildings[pos.y * w + pos.x]
            b2 = state.buildings[sy * w + sx]
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

    state.symmetry_candidates -= invalid

    if state.symmetry is None and len(state.symmetry_candidates) == 1:
        state.symmetry = next(iter(state.symmetry_candidates))
