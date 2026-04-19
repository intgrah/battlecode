from __future__ import annotations

from typing import TYPE_CHECKING

from hardcode.known import KnownMap

from builder.role import Role

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder

_OPENING_ROLES = [
    (Role.ECON, True),
    (Role.ECON, False),
    (Role.DEFENSE, True),
    (Role.OFFENSE, True),
    (Role.OFFENSE, True),
    (Role.ECON, False),
]

_SOCKET_OPENING_ROLES = [
    (Role.ECON, True),
    (Role.ECON, False),
    (Role.SOCKET_GUARD_1, True),
    (Role.SOCKET_GUARD_2, True),
    (Role.OFFENSE, True),
    (Role.OFFENSE, True),
]

_TILES_OPENING_ROLES = [
    (Role.ECON, True),
    (Role.TILES_GUARD_1, True),
    (Role.TILES_GUARD_2, True),
    (Role.TILES_GUARD_3, True),
    (Role.OFFENSE, True),
    (Role.OFFENSE, True),
]

_WINDOW_SHOPPING_OPENING_ROLES = [
    (Role.ECON, True),
    (Role.ECON, False),
    (Role.WINDOW_SHOPPING_GUARD, True),
]

_CRATERS_OPENING_ROLES = [
    (Role.ECON, True),
    (Role.ECON, False),
    (Role.ECON, False),
]

_CHESS_OPENING_ROLES = [
    (Role.ECON, True),
    (Role.ECON, False),
    (Role.ECON, False),
]

_DNA_OPENING_ROLES = [
    (Role.ECON, True),
    (Role.ECON, False),
    (Role.ECON, False),
]

_RUSH_BAIT_OPENING_ROLES = [
    (Role.ECON, True),
    (Role.ECON, False),
    (Role.ECON, False),
]

_PONG_OPENING_ROLES = [
    (Role.ECON, True),
    (Role.ECON, False),
    (Role.ECON, False),
]

_BEAR_OF_DOOM_OPENING_ROLES = [
    (Role.ECON, True),
    (Role.ECON, False),
    (Role.ECON, False),
]

_INITIAL_WEIGHTS = {
    True: {Role.DEFENSE: 6, Role.ECON: 3},
    False: {Role.DEFENSE: 3, Role.ECON: 3},
}

_TRANSITION: dict[Role, dict[Role, int]] = {
    Role.ECON: {Role.DEFENSE: 5, Role.ECON: 95},
    Role.DEFENSE: {Role.DEFENSE: 80, Role.ECON: 20},
    Role.OFFENSE: {Role.OFFENSE: 100},
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
    if self.known_map == KnownMap.SOCKET:
        opening = _SOCKET_OPENING_ROLES
    elif self.known_map == KnownMap.TILES:
        opening = _TILES_OPENING_ROLES
    elif self.known_map == KnownMap.WINDOW_SHOPPING:
        opening = _WINDOW_SHOPPING_OPENING_ROLES
    elif self.known_map == KnownMap.CRATERS:
        opening = _CRATERS_OPENING_ROLES
    elif self.known_map == KnownMap.CHESS:
        opening = _CHESS_OPENING_ROLES
    elif self.known_map == KnownMap.DNA:
        opening = _DNA_OPENING_ROLES
    elif self.known_map == KnownMap.RUSH_BAIT:
        opening = _RUSH_BAIT_OPENING_ROLES
    elif self.known_map == KnownMap.PONG:
        opening = _PONG_OPENING_ROLES
    elif self.known_map == KnownMap.BEAR_OF_DOOM:
        opening = _BEAR_OF_DOOM_OPENING_ROLES
    else:
        opening = _OPENING_ROLES
    if 0 <= idx < len(opening):
        role, perm = opening[idx]
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
