from cambc import Controller, Direction, Position

from .helpers import make_move
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
    my_pos = ct.get_position()
    if state.patrol_head:
        if my_pos.distance_squared(state.patrol_head) > PATROL_RANGE:
            make_move(state, ct, state.patrol_head)
            return True
        conveyors = state.get_conveyors_to_here(state.patrol_head)
        if len(conveyors) == 0:
            state.patrol_head = None
            state.patrol_trail = []
            make_move(state, ct, state.my_core)
            return True
        while (
            len(conveyors) > 0
            and my_pos.distance_squared(state.patrol_head) <= PATROL_RANGE
        ):
            state.rng.shuffle(conveyors)
            state.patrol_head = conveyors[0]
            conveyors = state.get_conveyors_to_here(state.patrol_head)
            if state.patrol_head in state.patrol_trail:
                state.patrol_head = None
                state.patrol_trail = []
                make_move(state, ct, state.my_core)
                return True
            state.patrol_trail.append(state.patrol_head)
        make_move(state, ct, state.patrol_head)
        return True
    if my_pos == state.my_core or (
        my_pos.distance_squared(state.my_core) <= 8
        and not ct.can_move(my_pos.direction_to(state.my_core))
    ):
        conveyors = core_feeders(state)
        if len(conveyors) > 0:
            state.rng.shuffle(conveyors)
            state.patrol_head = conveyors[0]
            state.patrol_trail = []
            make_move(state, ct, state.patrol_head)
            return True
        return False
    make_move(state, ct, state.my_core)
    return True
