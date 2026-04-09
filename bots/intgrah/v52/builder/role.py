from enum import IntEnum
from typing import Final


class Role(IntEnum):
    ECON = 0
    DEFENSE = 1
    OFFENSE = 2

    def __str__(self) -> str:
        return self.name.lower()


ROLE_WEIGHTS: Final[dict[bool, dict[Role, int]]] = {
    True: {Role.DEFENSE: 6, Role.OFFENSE: 1, Role.ECON: 3},
    False: {Role.DEFENSE: 3, Role.OFFENSE: 4, Role.ECON: 3},
}

ROLE_TRANSITION: dict[Role, dict[Role, int]] = {
    Role.ECON: {Role.OFFENSE: 60, Role.DEFENSE: 5, Role.ECON: 35},
    Role.DEFENSE: {Role.OFFENSE: 10, Role.DEFENSE: 80, Role.ECON: 10},
    Role.OFFENSE: {Role.OFFENSE: 60, Role.DEFENSE: 0, Role.ECON: 40},
}


ROLE_OPENING: Final[tuple[tuple[Role, bool], ...]] = (
    (Role.ECON, True),
    (Role.ECON, False),
    (Role.DEFENSE, True),
    (Role.OFFENSE, False),
    (Role.OFFENSE, False),
    (Role.OFFENSE, False),
)

ROLE_REASSIGN_PERIOD: Final[int] = 150
ROLE_REASSIGN_AFTER: Final[int] = 400
