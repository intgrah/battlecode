from cambc import Controller

from builder.state import State
from builder.state.role import Role

_OPENING_ROLES = [
    (Role.ECON, True, 0),
    (Role.ECON, False, 1),
    (Role.DEFENSE, True, None),
    (Role.OFFENSE, False, None),
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
