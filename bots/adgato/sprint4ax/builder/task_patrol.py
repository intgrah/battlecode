from cambc import Controller, Direction, EntityType, Position

from .helpers import make_move, make_multi_move
from .state import State


def trace_upstream(state: State, position: Position) -> list[Position]:
    path: list[Position] = []
    conveyors = [position]
    while len(conveyors) > 0:
        state.rng.shuffle(conveyors)
        position = conveyors[0]
        conveyors = state.get_conveyors_to_here(position)
        if position in path:
            break
        path.append(position)
    return path


PATROL_RANGE = 4


def core_feeders(state: State) -> list[Position]:
    return [
        pos
        for d in Direction
        for pos in state.get_conveyors_to_here(state.my_core.add(d))
    ]

def run_patrol(state: State, ct: Controller) -> bool:
    my_team = ct.get_team()
    c_rnd = ct.get_current_round()

    if state.patrol_head and ct.is_in_vision(state.patrol_head):
        for unit in ct.get_nearby_units():
            if ct.get_entity_type(unit) != EntityType.BUILDER_BOT or ct.get_team(unit) != my_team:
                continue
            if ct.get_position(unit).distance_squared(state.patrol_head) <= PATROL_RANGE:
                state.patrol_head = None
                break
        
    if state.patrol_head is None and state.patrol_queue:
        state.patrol_head = max(state.patrol_queue, key=lambda v: (c_rnd - v[1]) * v[2])[0]

    if state.patrol_head:
        make_move(state, ct, state.patrol_head)

    return state.patrol_queue
