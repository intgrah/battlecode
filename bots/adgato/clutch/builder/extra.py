from building import BuildingHarvester, BuildingRoad
from cambc import Controller, Environment, Position
from util import DIR4

from .helpers import try_move_adj_to
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


def pave(state: State, ct: Controller, maybe_unpaved: list[Position]) -> bool:
    my_team = ct.get_team()
    for pos in maybe_unpaved:
        bid = ct.get_tile_building_id(pos)
        if bid is not None and ct.get_team(bid) != my_team:
            continue

        # Pick a conveyor direction: prefer pointing into a friendly
        # harvester (so the chain can be extended back to core), else
        # toward an adjacent unmined ore tile.
        direction = None
        for d in DIR4:
            building = state.get_building(pos.add(d))
            if isinstance(building, BuildingHarvester) and building.team == my_team:
                direction = d
                break
        else:
            ore_env = (Environment.ORE_AXIONITE, Environment.ORE_TITANIUM)
            for d in DIR4:
                if (
                    state.get_building(pos.add(d)) is None
                    and state.get_env(pos.add(d)) in ore_env
                ):
                    direction = d
                    break
        if direction is None:
            continue

        is_road = isinstance(state.get_building(pos), BuildingRoad)
        moved = False
        my_pos = ct.get_position()
        if my_pos.distance_squared(pos) > 2 and (bid is None or is_road):
            moved = try_move_adj_to(ct, pos)
            if not moved:
                continue

        if is_road and ct.can_destroy(pos):
            ct.destroy(pos)

        if ct.can_build_conveyor(pos, direction):
            ct.build_conveyor(pos, direction)
            return True

        if moved:
            return False
    return False


def pave_near_harvesters(state: State, ct: Controller) -> bool:
    # Pave conveyors (not roads) adjacent to harvesters. Chain connection
    # is handled by the separate _connect_close / _connect_far tasks
    # via state.dangling_output, so we don't need to call route_to_core
    # here.
    my_pos = ct.get_position()
    candidates = [
        pos
        for pos in ct.get_nearby_tiles(8)
        if pos in state.adjacent_to_harvester
        and state.get_env(pos) != Environment.WALL
    ]
    candidates.sort(key=my_pos.distance_squared)
    return pave(state, ct, candidates)
