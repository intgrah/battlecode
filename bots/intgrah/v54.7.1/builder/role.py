from enum import IntEnum


class Role(IntEnum):
    ECON = 0
    DEFENSE = 1
    OFFENSE = 2
    OFFENSIVE_PUSH = 3

    def __str__(self) -> str:
        return self.name.lower()
