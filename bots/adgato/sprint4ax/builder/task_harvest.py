from building import (
    BuildingBridge,
    BuildingConveyor,
    BuildingHarvester,
    BuildingRoad,
    BuildingSplitter,
)
from cambc import Controller, EntityType, Environment, Position
from util import DIR4, INF, can_afford, get_direction_object

from .algorithms.pathfind import conv_pathfind
from .helpers import make_move, try_move_with_road
from .state import State


def _find_contest_target(state: State, pos: Position, my_team) -> Position | None:
    """Return the first enemy contestable building (road, conveyor,
    splitter, bridge) adjacent to `pos` that we can destroy by
    standing on it and firing. Roads are included: even though they
    don't siphon Ti directly, an enemy holding roads around our ore
    can upgrade them to conveyors next turn and start siphoning.

    Non-contestable enemies (armoured conveyors, turrets, foundries,
    cores, barriers) are intentionally NOT returned — we can't damage
    or walk on them. The harvester still gets built and we accept the
    fractional Ti leakage.
    """
    for d in DIR4:
        n = pos.add(d)
        if not state.in_bounds(n):
            continue
        b = state.get_building(n)
        if b is None or getattr(b, "team", None) == my_team:
            continue
        if isinstance(
            b, (BuildingRoad, BuildingConveyor, BuildingSplitter, BuildingBridge)
        ):
            return n
    return None


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
    current_pos = ct.get_position()

    best_target = None
    min_dist = INF

    for pos in ct.get_nearby_tiles():
        terrain = state.get_env(pos)

        if terrain == Environment.ORE_TITANIUM:
            match state.get_building(pos):
                case BuildingHarvester():
                    continue
                case None | BuildingRoad():
                    pass
                case _:
                    continue

            if ore_available(state, ct, pos):
                dist = current_pos.distance_squared(pos)
                if dist < min_dist:
                    min_dist = dist
                    best_target = pos

    return best_target


def build_at_ore(state: State, ct: Controller, target_pos: Position) -> bool:
    my_pos = ct.get_position()

    # Contest step: if an enemy road/conveyor/splitter/bridge is
    # sitting adjacent to this ore, clear it before building the
    # harvester. `pathfind_blocked` can't step onto an impassable
    # (INF cost) goal because the path-extraction formula adds the
    # goal's cost, so for the final step we use a direct ct.move()
    # in the right direction.
    contest_pos = _find_contest_target(state, target_pos, ct.get_team())
    if contest_pos is not None:
        if my_pos == contest_pos:
            ti, _ = ct.get_global_resources()
            if ti >= 2 and ct.can_fire(my_pos):
                ct.fire(my_pos)
            return True
        if my_pos.distance_squared(contest_pos) <= 2:
            d = my_pos.direction_to(contest_pos)
            if ct.can_move(d):
                ct.move(d)
            return True
        make_move(state, ct, contest_pos)
        return True

    if my_pos == target_pos:
        if not ore_available(state, ct, target_pos):
            state.ore_target = None
            return False

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
        if not can_afford(ct, EntityType.HARVESTER):
            if try_move_with_road(ct, target_pos):
                return True
            return True

        has_road = isinstance(state.get_building(target_pos), BuildingRoad)

        if has_road:
            if try_move_with_road(ct, target_pos):
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
                    ) and try_move_with_road(ct, ortho_pos):
                        return True

                if try_move_with_road(ct, target_pos):
                    return True

                return True

            if ct.can_build_harvester(target_pos):
                ct.build_harvester(target_pos)
                state.ore_target = None
                return True

    return make_move(state, ct, target_pos)
