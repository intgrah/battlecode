from enum import IntEnum


class Role(IntEnum):
    ECON = 0
    DEFENSE = 1
    OFFENSE = 2
    SOCKET_GUARD_1 = 3
    SOCKET_GUARD_2 = 4

    def __str__(self) -> str:
        return self.name.lower()
