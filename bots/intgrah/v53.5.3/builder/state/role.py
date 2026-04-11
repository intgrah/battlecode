from enum import IntEnum


class Role(IntEnum):
    ECON = 0
    DEFENSE = 1
    OFFENSE = 2
    PERM_ECON = 3
    PERM_OFFENSE = 4
    PERM_DEFENSE = 5

    def __str__(self) -> str:
        return self.name.lower()
