from __future__ import annotations

from typing import TYPE_CHECKING, Final

from builder.role import Role

if TYPE_CHECKING:
    from builder import Builder


_OPENING_ROLES: Final = [
    Role.PARASITIC,
    Role.PERM_ECON,
    Role.ECON_REACTIVE,
    Role.ECON,
]

_ECON_REACTIVE_FLIP_ROUND: Final = 25
"""ECON_REACTIVE auto-flips to DEFENSE once `self.round` exceeds this.
Picks up an early-game economic-map snapshot before pivoting."""

# Offence weight is split 50-50 between PUSH and PARASITIC at every
# stage. Sums chosen so the integer split is exact (each takes half
# of what OFFENSE used to get).
_INITIAL_WEIGHTS_VERY_EARLY: Final = {
    Role.DEFENSE: 3,
    Role.PUSH: 0,
    Role.PARASITIC: 3,
    Role.ECON: 4,
}
_INITIAL_WEIGHTS_EARLY: Final = {
    Role.DEFENSE: 5,
    Role.PUSH: 1,
    Role.PARASITIC: 1,
    Role.ECON: 3,
}
_INITIAL_WEIGHTS_LATE: Final = {
    Role.DEFENSE: 3,
    Role.PUSH: 2,
    Role.PARASITIC: 2,
    Role.ECON: 3,
}


_TRANSITION: Final[dict[Role, dict[Role, int]]] = {
    Role.ECON: {
        Role.PUSH: 30,
        Role.PARASITIC: 30,
        Role.DEFENSE: 5,
        Role.ECON: 35,
    },
    Role.DEFENSE: {
        Role.PUSH: 5,
        Role.PARASITIC: 5,
        Role.DEFENSE: 80,
        Role.ECON: 10,
    },
    Role.PUSH: {Role.PUSH: 60, Role.DEFENSE: 0, Role.ECON: 40},
    Role.PARASITIC: {Role.PARASITIC: 60, Role.DEFENSE: 0, Role.ECON: 40},
    Role.PERM_ECON: {Role.PERM_ECON: 1},
    Role.PERM_DEFENSE: {Role.PERM_DEFENSE: 1},
}

_REASSIGN_PERIOD: Final = 150
_REASSIGN_AFTER: Final = 400


def _pick_initial_role(self: Builder) -> Role:
    """Opening spawn slots use the hardcoded sequence indexed by the
    builder's spawn round, since `get_unit_count()` is non-monotonic
    — a builder dying mid-opening (or any round where the core
    couldn't spawn) makes two later spawns share the same count and
    pick the same opening slot. Round number always advances, so each
    opening slot is unique. Once the opening sequence is exhausted,
    fall back to a weighted random pick biased by game stage (early
    defence-heavy, mid more aggressive).
    """
    idx = self.round - 1
    if 0 <= idx < len(_OPENING_ROLES):
        return _OPENING_ROLES[idx]
    w = (
        _INITIAL_WEIGHTS_VERY_EARLY
        if self.round < 50
        else _INITIAL_WEIGHTS_EARLY
        if self.round < 200
        else _INITIAL_WEIGHTS_LATE
    )
    roles, weights = zip(*w.items(), strict=False)
    return self.rng.choices(roles, weights=weights)[0]


def update_role(self: Builder) -> None:
    if self.role is None:
        self.role = _pick_initial_role(self)
    if (
        self.role == Role.ECON_REACTIVE
        and self.round > _ECON_REACTIVE_FLIP_ROUND
    ):
        self.role = Role.DEFENSE
        self.role_age = 0
    if self.role_age > _REASSIGN_PERIOD and self.round > _REASSIGN_AFTER:
        self.role_age = 0
        row = _TRANSITION[self.role]
        roles, weights = zip(*row.items(), strict=False)
        self.role = self.rng.choices(roles, weights=weights)[0]
        if self.role.is_offensive():
            self.role_age = -300
    self.role_age += 1
