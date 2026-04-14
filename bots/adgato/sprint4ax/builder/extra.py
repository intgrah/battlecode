from building import BuildingHarvester, BuildingRoad
from cambc import Controller, Direction, Environment

from .helpers import DIR4, try_move_adj_to
from .state import State


def fix_enemy_conveyor(state: State, ct: Controller) -> bool:
    nearby_positions = ct.get_nearby_tiles(2)
    for pos in nearby_positions:
        if state.leads_to_enemy_building(pos) and ct.can_destroy(pos):
            ct.destroy(pos)
            if ct.can_build_road(pos):
                ct.build_road(pos)
                return True
    return False


def deny_enemy_ore(state: State, ct: Controller) -> bool:
    """Opportunistic ore denial: drop a cheap road on a tile that
    would be a harvester-feed candidate for an enemy. Only acts when
    a denial tile is already within action range — no repositioning.
    """
    nearby_positions = ct.get_nearby_tiles(2)
    for pos in nearby_positions:
        if pos not in state.deny_ore_neighbours:
            continue
        if state.get_env(pos) == Environment.WALL:
            continue
        if state.get_building(pos) is not None:
            continue
        if ct.can_build_road(pos):
            ct.build_road(pos)
            return True
    return False


def pave_near_harvesters(state: State, ct: Controller) -> bool:
    # Always prefer conveyors adjacent to harvesters. Chain connection
    # is handled by the separate _connect_close / _connect_far tasks
    # via state.dangling_output, so we don't need to call
    # route_to_core here.

    candidates = [
        pos
        for pos in ct.get_nearby_tiles(8)
        if pos in state.adjacent_to_harvester and state.get_env(pos) != Environment.WALL
    ]
    maybe_unpaved = sorted(candidates, key=ct.get_position().distance_squared)

    my_team = ct.get_team()
    for pos in maybe_unpaved:
        bid = ct.get_tile_building_id(pos)
        if bid is not None and ct.get_team(ct.get_tile_building_id(pos)) != my_team:
            continue

        dir = Direction.CENTRE
        for d in DIR4:
            building = state.get_building(pos.add(d))
            if isinstance(building, BuildingHarvester):
                if building.team == my_team:
                    dir = d
                    break

        is_road = isinstance(state.get_building(pos), BuildingRoad)
        moved = False
        if ct.get_position().distance_squared(pos) > 2 and (bid is None or is_road):
            moved = try_move_adj_to(ct, pos)
            if not moved:
                continue

        if is_road and ct.can_destroy(pos):
            ct.destroy(pos)

        if ct.can_build_conveyor(pos, dir):
            ct.build_conveyor(pos, dir)
            return True

        if moved:
            return False

    return False
