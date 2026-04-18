from enum import IntEnum


class Role(IntEnum):
    ECON = 0
    DEFENSE = 1
    OFFENSE = 2
    SOCKET_GUARD_1 = 3
    SOCKET_GUARD_2 = 4
    TILES_GUARD_1 = 5
    TILES_GUARD_2 = 6
    TILES_GUARD_3 = 7

    def __str__(self) -> str:
        return self.name.lower()
