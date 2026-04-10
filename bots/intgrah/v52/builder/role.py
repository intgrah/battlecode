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
    Role.ECON: {Role.OFFENSE: 12, Role.DEFENSE: 1, Role.ECON: 7},
    Role.DEFENSE: {Role.OFFENSE: 2, Role.DEFENSE: 16, Role.ECON: 2},
    Role.OFFENSE: {Role.OFFENSE: 12, Role.DEFENSE: 0, Role.ECON: 8},
}


ROLE_OPENING: Final[tuple[Role, ...]] = (
    Role.ECON,
    Role.ECON,
    Role.DEFENSE,
    Role.OFFENSE,
    Role.OFFENSE,
    Role.OFFENSE,
)
