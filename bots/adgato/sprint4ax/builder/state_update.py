from building import BuildingArmouredConveyor, BuildingConveyor
from cambc import Controller
from config import DEBUG_TIMING
from util import DIR8

from .role import Role
from .state import State
from .task_harvest import ore_available, pick_ore_target
from .task_repair import find_dangling, is_dangling

_OPENING_ROLES = [
    (Role.ECON, True, 0),
    (Role.ECON, False, 1),
    (Role.DEFENSE, True, None),
    (Role.OFFENSE, False, None),
    (Role.OFFENSE, False, None),
]

_INITIAL_WEIGHTS = {
    True: {Role.DEFENSE: 6, Role.OFFENSE: 1, Role.ECON: 3},
    False: {Role.DEFENSE: 3, Role.OFFENSE: 4, Role.ECON: 3},
}

_TRANSITION: dict[Role, dict[Role, int]] = {
    Role.ECON: {Role.OFFENSE: 60, Role.DEFENSE: 5, Role.ECON: 35},
    Role.DEFENSE: {Role.OFFENSE: 10, Role.DEFENSE: 80, Role.ECON: 10},
    Role.OFFENSE: {Role.OFFENSE: 60, Role.DEFENSE: 0, Role.ECON: 40},
}

_REASSIGN_PERIOD = 150
_REASSIGN_AFTER = 400


def _pick_initial_role(state: State, ct: Controller) -> Role:
    if ct.get_current_round() > 10:
        early = ct.get_current_round() < 200
        w = _INITIAL_WEIGHTS[early]
        roles, weights = zip(*w.items(), strict=False)
        return state.rng.choices(roles, weights=weights)[0]
    idx = ct.get_unit_count() - 3
    if 0 <= idx < len(_OPENING_ROLES):
        role, perm, scout_dir = _OPENING_ROLES[idx]
        state.permanent_role = perm
        if scout_dir is not None:
            state.scout_active = True
            state.scout_direction = scout_dir
        return role
    return Role.ECON


def update_role(state: State, ct: Controller) -> None:
    if state.role is None:
        state.role = _pick_initial_role(state, ct)
    if ct.get_current_round() > 25:
        state.scout_active = False

    if (
        state.role_age > _REASSIGN_PERIOD
        and ct.get_current_round() > _REASSIGN_AFTER
        and not state.permanent_role
    ):
        state.role_age = 0
        row = _TRANSITION[state.role]
        roles, weights = zip(*row.items(), strict=False)
        state.role = state.rng.choices(roles, weights=weights)[0]
        if state.role == Role.OFFENSE:
            state.role_age = -300

    state.role_age += 1


def _update_dangling(state: State, ct: Controller) -> None:
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


def _update_ore_target(state: State, ct: Controller) -> None:
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


def update_economy(state: State, ct: Controller) -> None:
    if DEBUG_TIMING:
        t0 = ct.get_cpu_time_elapsed()
        _update_dangling(state, ct)
        t1 = ct.get_cpu_time_elapsed()
        print(f"  loose={t1 - t0}us")
        _update_ore_target(state, ct)
        t2 = ct.get_cpu_time_elapsed()
        print(f"  ore={t2 - t1}us")
    else:
        _update_dangling(state, ct)
        _update_ore_target(state, ct)
