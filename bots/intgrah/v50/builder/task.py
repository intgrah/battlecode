from enum import IntEnum, auto


class Role(IntEnum):
    ECON = 0
    DEFENSE = 1
    OFFENSE = 2


class Task(IntEnum):
    CONNECT_EXCESS_TI = auto()
    CONNECT_EXCESS_AX = auto()
    HARVEST_TI = auto()
    HARVEST_AX = auto()
    EXPLORE = auto()
    PATROL = auto()
    HEAL_CORE = auto()
    PLACE_LAUNCHER = auto()
    BARRIER_ORE = auto()
    FIRE_ENEMY_TRANSPORT = auto()
    PLACE_SENTINEL = auto()
    HEAL_TURRET = auto()
