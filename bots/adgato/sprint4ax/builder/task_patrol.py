from cambc import Controller, Direction, Position, EntityType

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
    my_pos = ct.get_position()
    my_team = ct.get_team()
    dist_to_me = my_pos.distance_squared

    if state.patrol_head:

        mark = [
            opp_pos
            for uid in ct.get_nearby_units() 
            if ct.get_entity_type(uid) == EntityType.BUILDER_BOT and \
               my_team != ct.get_team(uid) and \
               (opp_pos := ct.get_position(uid)).distance_squared(state.patrol_head) <= PATROL_RANGE
        ]
        enemies_near_head = bool(mark)
        if not enemies_near_head:
            mark.append(state.patrol_head)

        if dist_to_me(state.patrol_head) > PATROL_RANGE:
            make_multi_move(state, ct, mark)
            return True
        conveyors = state.get_conveyors_to_here(state.patrol_head)
        if len(conveyors) == 0:
            state.patrol_head = None
            state.patrol_trail = []
            make_move(state, ct, state.my_core)
            return True
        
        if not enemies_near_head:
            while (
                len(conveyors) > 0
                and dist_to_me(state.patrol_head) <= PATROL_RANGE
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

        make_multi_move(state, ct, mark)
        return True
    
    dist_to_core = dist_to_me(state.my_core)
    if dist_to_core <= 2 or (
        dist_to_core <= 8 and not ct.can_move(my_pos.direction_to(state.my_core))
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
