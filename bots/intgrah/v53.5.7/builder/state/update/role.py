from typing import Final

from cambc import Controller

from builder.state import State
from builder.state.role import Role

_OPENING_ROLES: Final[list[Role]] = [
    Role.PERM_ECON,
    Role.ECON,
    Role.PERM_DEFENSE,
    Role.OFFENSE,
    Role.OFFENSE,
    Role.OFFENSE,
]

_INITIAL_WEIGHTS = {
    True: {Role.DEFENSE: 6, Role.OFFENSE: 1, Role.ECON: 3},
    False: {Role.DEFENSE: 3, Role.OFFENSE: 4, Role.ECON: 3},
}

_TRANSITION: dict[Role, dict[Role, int]] = {
    Role.ECON: {Role.OFFENSE: 60, Role.DEFENSE: 5, Role.ECON: 35},
    Role.DEFENSE: {Role.OFFENSE: 10, Role.DEFENSE: 80, Role.ECON: 10},
    Role.OFFENSE: {Role.OFFENSE: 60, Role.DEFENSE: 0, Role.ECON: 40},
    Role.PERM_ECON: {Role.PERM_ECON: 1},
    Role.PERM_OFFENSE: {Role.PERM_OFFENSE: 1},
    Role.PERM_DEFENSE: {Role.PERM_DEFENSE: 1},
}

_REASSIGN_PERIOD: Final[int] = 150
_REASSIGN_AFTER: Final[int] = 400


def _pick_initial_role(state: State, ct: Controller) -> Role:
    if ct.get_current_round() > 10:
        early = ct.get_current_round() < 200
        w = _INITIAL_WEIGHTS[early]
        roles, weights = zip(*w.items(), strict=False)
        return state.rng.choices(roles, weights=weights)[0]
    idx = ct.get_unit_count() - 3
    if idx < len(_OPENING_ROLES):
        return _OPENING_ROLES[idx]
    return Role.ECON


def update_role(state: State, ct: Controller) -> None:
    if state.role is None:
        state.role = _pick_initial_role(state, ct)

    if state.role_age > _REASSIGN_PERIOD and ct.get_current_round() > _REASSIGN_AFTER:
        state.role_age = 0
        row = _TRANSITION[state.role]
        roles, weights = zip(*row.items(), strict=False)
        state.role = state.rng.choices(roles, weights=weights)[0]
        if state.role == Role.OFFENSE:
            state.role_age = -300

    state.role_age += 1
