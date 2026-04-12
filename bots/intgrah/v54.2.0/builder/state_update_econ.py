from building import BuildingArmouredConveyor, BuildingConveyor
from cambc import Controller
from util import DIR8

from .helpers import find_dangling, is_dangling, ore_available, pick_ore_target
from .state import State


def update_dangling(state: State, ct: Controller) -> None:
    my_pos = ct.get_position()
    if is_dangling(state, ct, my_pos):
        state.dangling_output = my_pos
    else:
        match state.get_building(my_pos):
            case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
                target = my_pos.add(d)
                if is_dangling(state, ct, target):
                    state.dangling_output = target
            case _:
                for d in DIR8:
                    n = my_pos.add(d)
                    if is_dangling(state, ct, n):
                        state.dangling_output = n
                        break
    if state.pending_bridge:
        state.dangling_output = state.pending_bridge
    elif state.dangling_output is None or not is_dangling(
        state, ct, state.dangling_output
    ):
        state.dangling_output = find_dangling(state, ct)


def update_ore_target(state: State, ct: Controller) -> None:
    my_pos = ct.get_position()
    candidate_ore = pick_ore_target(state, ct)
    if (
        not state.ore_target
        or not ore_available(state, ct, state.ore_target)
        or (
            candidate_ore
            and candidate_ore.distance_squared(my_pos) <= 2
            and state.ore_target.distance_squared(my_pos) > 2
        )
    ):
        state.ore_target = candidate_ore
