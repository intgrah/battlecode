from __future__ import annotations

from typing import Final

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from builder import Builder
from builder.role import Role
_OPENING_ROLES: Final[list[Role]] = [Role.Parasitic, Role.PermEcon, Role.EconReactive, Role.Econ]
_ECON_REACTIVE_FLIP_ROUND: Final[int] = 25
"""
`ECON_REACTIVE` auto-flips to DEFENSE once `self.round` exceeds this.
Picks up an early-game economic-map snapshot before pivoting.
"""
_INITIAL_WEIGHTS_VERY_EARLY: Final[list[tuple[Role, int]]] = [(Role.Defense, 3), (Role.Push, 0), (Role.Parasitic, 3), (Role.Econ, 4)]
_INITIAL_WEIGHTS_EARLY: Final[list[tuple[Role, int]]] = [(Role.Defense, 5), (Role.Push, 1), (Role.Parasitic, 1), (Role.Econ, 3)]
_INITIAL_WEIGHTS_LATE: Final[list[tuple[Role, int]]] = [(Role.Defense, 3), (Role.Push, 2), (Role.Parasitic, 2), (Role.Econ, 3)]
_TRANSITION_ECON: Final[list[tuple[Role, int]]] = [(Role.Push, 30), (Role.Parasitic, 30), (Role.Defense, 5), (Role.Econ, 35)]
_TRANSITION_DEFENSE: Final[list[tuple[Role, int]]] = [(Role.Push, 5), (Role.Parasitic, 5), (Role.Defense, 80), (Role.Econ, 10)]
_TRANSITION_PUSH: Final[list[tuple[Role, int]]] = [(Role.Push, 60), (Role.Defense, 0), (Role.Econ, 40)]
_TRANSITION_PARASITIC: Final[list[tuple[Role, int]]] = [(Role.Parasitic, 60), (Role.Defense, 0), (Role.Econ, 40)]
_TRANSITION_PERM_ECON: Final[list[tuple[Role, int]]] = [(Role.PermEcon, 1)]
_TRANSITION_PERM_DEFENSE: Final[list[tuple[Role, int]]] = [(Role.PermDefense, 1)]

def _transition_for(role):
    match role:
        case Role.Econ:
            return _TRANSITION_ECON
        case Role.Defense:
            return _TRANSITION_DEFENSE
        case Role.Push:
            return _TRANSITION_PUSH
        case Role.Parasitic:
            return _TRANSITION_PARASITIC
        case Role.PermEcon:
            return _TRANSITION_PERM_ECON
        case Role.PermDefense:
            return _TRANSITION_PERM_DEFENSE
        case Role.EconReactive:
            return _TRANSITION_ECON
_REASSIGN_PERIOD: Final[int] = 150
_REASSIGN_AFTER: Final[int] = 400

def weighted_choice(builder, choices):
    total: int = sum((t[1] for t in choices))
    if total == 0:
        return choices[0][0]
    population: list[Role] = list((t[0] for t in choices))
    weights: list[float] = list((float(t[1]) for t in choices))
    return builder.state.rng.choices(population, weights, k=1)[0]

def _pick_initial_role(builder):
    """
    Opening spawn slots use the hardcoded sequence indexed by the
    builder's spawn round, since `get_unit_count()` is non-monotonic
    — a builder dying mid-opening (or any round where the core
    couldn't spawn) makes two later spawns share the same count and
    pick the same opening slot. Round number always advances, so each
    opening slot is unique. Once the opening sequence is exhausted,
    fall back to a weighted random pick biased by game stage (early
    defence-heavy, mid more aggressive).
    """
    idx = builder.state.round - 1
    if (idx in range(0, int(len(_OPENING_ROLES)))):
        return _OPENING_ROLES[int(idx)]
    w: list[tuple[Role, int]] = _INITIAL_WEIGHTS_VERY_EARLY if builder.state.round < 50 else (_INITIAL_WEIGHTS_EARLY if builder.state.round < 200 else _INITIAL_WEIGHTS_LATE)
    return weighted_choice(builder, w)

def update_role(builder):
    if (builder.role is None):
        builder.role = _pick_initial_role(builder)
    if builder.role == Role.EconReactive and builder.state.round > 25:
        builder.role = Role.Defense
        builder.role_age = 0
    if builder.role_age > 150 and builder.state.round > 400:
        builder.role_age = 0
        row = _transition_for(builder.role)
        new_role = weighted_choice(builder, row)
        builder.role = new_role
        if new_role.is_offensive():
            builder.role_age = -300
    builder.role_age += 1
