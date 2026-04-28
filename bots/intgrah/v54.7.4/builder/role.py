from enum import IntEnum


class Role(IntEnum):
    ECON = 0
    DEFENSE = 1
    OFFENSE = 2
    PERM_ECON = 3
    PERM_DEFENSE = 4

    def __str__(self) -> str:
        return self.name.lower()
