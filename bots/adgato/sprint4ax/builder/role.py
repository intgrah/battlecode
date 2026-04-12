from enum import IntEnum


class Role(IntEnum):
    ECON = 0
    DEFENSE = 1
    OFFENSE = 2

    def __str__(self) -> str:
        return self.name.lower()
