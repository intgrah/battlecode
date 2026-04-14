from cambc import Controller, Environment

from .state import State


def fix_enemy_conveyor(state: State, ct: Controller) -> bool:
    for pos in ct.get_nearby_tiles():
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
    for pos in ct.get_nearby_tiles():
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
    """Always prefer roads adjacent to harvesters. Chain connection
    is handled by the separate _connect_close / _connect_far tasks
    via state.dangling_output, so we don't need to call
    route_to_core here. Roads are 1 Ti (vs 3 Ti conveyor) and
    keep the harvester-halo cheap.
    """
    for pos in ct.get_nearby_tiles():
        if (
            pos in state.adjacent_to_harvester
            and not state.get_building(pos)
            and state.get_env(pos) != Environment.WALL
            and ct.can_build_road(pos)
        ):
            ct.build_road(pos)
            return True
    return False
