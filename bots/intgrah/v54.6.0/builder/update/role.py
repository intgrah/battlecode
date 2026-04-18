from __future__ import annotations

from typing import TYPE_CHECKING

from builder.role import Role

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder

_OPENING_ROLES = [
    (Role.ECON, True),
    (Role.ECON, False),
    (Role.DEFENSE, True),
    (Role.OFFENSE, False),
    (Role.OFFENSE, False),
    (Role.OFFENSE, False),
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


def _pick_initial_role(self: Builder, ct: Controller) -> Role:
    if self.round > 10:
        early = self.round < 200
        w = _INITIAL_WEIGHTS[early]
        roles, weights = zip(*w.items(), strict=False)
        return self.rng.choices(roles, weights=weights)[0]
    idx = ct.get_unit_count() - 3
    if 0 <= idx < len(_OPENING_ROLES):
        role, perm = _OPENING_ROLES[idx]
        self.permanent_role = perm
        return role
    return Role.ECON


def update_role(self: Builder, ct: Controller) -> None:
    if self.role is None:
        self.role = _pick_initial_role(self, ct)

    if (
        self.role_age > _REASSIGN_PERIOD
        and self.round > _REASSIGN_AFTER
        and not self.permanent_role
    ):
        self.role_age = 0
        row = _TRANSITION[self.role]
        roles, weights = zip(*row.items(), strict=False)
        self.role = self.rng.choices(roles, weights=weights)[0]
        if self.role == Role.OFFENSE:
            self.role_age = -300

    self.role_age += 1
