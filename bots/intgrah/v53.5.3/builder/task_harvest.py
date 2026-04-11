from building import BuildingHarvester, BuildingRoad
from cambc import Controller, EntityType, Environment, Position
from util import DIR4, INF, can_afford, get_direction_object

from .algorithms.astar import pathfind_move
from .algorithms.econ_astar import conv_pathfind
from .helpers import make_move, try_move_with_build
from .state import State


def ore_available(state: State, ct: Controller, pos: Position) -> bool:
    b = state.get_building(pos)
    if b is not None and not isinstance(b, BuildingRoad):
        return False

    if ct.is_in_vision(pos):
        worker_id = ct.get_tile_builder_bot_id(pos)
        if worker_id is not None and worker_id != ct.get_id():
            return False

    return True


def pick_ore_target(state: State, ct: Controller) -> Position | None:
    w = state.w
    nav_dist = state.nav_dist

    best_target = None
    min_dist = INF

    for pos in ct.get_nearby_tiles():
        terrain = state.get_env(pos)

        if terrain == Environment.ORE_TITANIUM or (
            terrain == Environment.ORE_AXIONITE and ct.get_current_round() >= 500
        ):
            match state.get_building(pos):
                case BuildingHarvester():
                    continue
                case None | BuildingRoad():
                    pass
                case _:
                    continue

            d = nav_dist[pos.y * w + pos.x]
            if d == -1:
                continue

            if ore_available(state, ct, pos) and d < min_dist:
                min_dist = d
                best_target = pos

    return best_target


def task_harvest_ti(state: State, ct: Controller, target_pos: Position) -> bool:
    my_pos = ct.get_position()

    neighbors = [target_pos.add(d) for d in DIR4]
    unpaved_neighbors = []
    for n in neighbors:
        if not state.in_bounds(n):
            continue
        if state.get_env(n) == Environment.WALL:
            continue

        b = state.get_building(n)
        if b is None:
            unpaved_neighbors.append(n)
        elif not isinstance(b, BuildingRoad):
            pass

    if my_pos == target_pos:
        if not ore_available(state, ct, target_pos):
            state.ore_target = None
            return False

        for n in unpaved_neighbors:
            if n == my_pos:
                continue
            if ct.can_build_road(n):
                ct.build_road(n)
                return True

        if not can_afford(ct, EntityType.HARVESTER):
            return True

        b = state.get_building(my_pos)
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
        if state.my_core:
            path = conv_pathfind(state, ct, my_pos, state.my_core)
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
            if state.is_passable(move_pos) and ct.can_move(d):
                ct.move(d)
                if ct.can_build_harvester(target_pos):
                    ct.build_harvester(target_pos)
                    state.ore_target = None
                return True

        return True

    if my_pos.distance_squared(target_pos) <= 2:
        if unpaved_neighbors:
            for n in unpaved_neighbors:
                if my_pos.distance_squared(n) <= 2 and ct.can_build_road(n):
                    ct.build_road(n)
                    return True

            target_has_road = isinstance(state.get_building(target_pos), BuildingRoad)

            if target_has_road:
                if try_move_with_build(state, ct, target_pos):
                    return True
            else:
                target_n = unpaved_neighbors[0]
                next_pos = pathfind_move(state, ct, my_pos, target_n)
                if next_pos is not None:
                    try_move_with_build(state, ct, next_pos)
                    return True
            return True

        if not can_afford(ct, EntityType.HARVESTER):
            if try_move_with_build(state, ct, target_pos):
                return True
            return True

        has_road = isinstance(state.get_building(target_pos), BuildingRoad)

        if has_road:
            if try_move_with_build(state, ct, target_pos):
                return True
        elif (
            ct.can_build_harvester(target_pos)
            and my_pos.distance_squared(target_pos) <= 1
        ):
            ct.build_harvester(target_pos)
            state.ore_target = None
            return True
        else:
            if my_pos.distance_squared(target_pos) > 1:
                for d in DIR4:
                    ortho_pos = target_pos.add(d)
                    if (
                        state.is_passable(ortho_pos)
                        and my_pos.distance_squared(ortho_pos) <= 2
                    ) and try_move_with_build(state, ct, ortho_pos):
                        return True

                if try_move_with_build(state, ct, target_pos):
                    return True

                return True

            if ct.can_build_harvester(target_pos):
                ct.build_harvester(target_pos)
                state.ore_target = None
                return True

    return make_move(state, ct, target_pos)
