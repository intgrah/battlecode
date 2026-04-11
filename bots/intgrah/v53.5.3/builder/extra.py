from cambc import Controller, Environment

from builder.helpers import is_dangling
from builder.state import State
from builder.task_build_conveyors import route_to_core


def fix_enemy_conveyor(state: State, ct: Controller) -> bool:
    nearby_positions = ct.get_nearby_tiles(2)
    for pos in nearby_positions:
        if state.leads_to_enemy_building(pos) and ct.can_destroy(pos):
            ct.destroy(pos)
            if ct.can_build_road(pos):
                ct.build_road(pos)
                return True
    return False


def pave_near_harvesters(state: State, ct: Controller) -> bool:
    nearby_positions = ct.get_nearby_tiles(2)
    for pos in nearby_positions:
        if (
            pos in state.adjacent_to_harvester
            and not state.get_building(pos)
            and state.get_env(pos) != Environment.WALL
        ):
            if is_dangling(state, ct, pos):
                route_to_core(state, ct, pos)
                return True
            if ct.can_build_road(pos):
                ct.build_road(pos)
                return True
    return False
