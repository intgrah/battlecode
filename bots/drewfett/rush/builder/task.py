from enum import IntEnum, auto


class Task(IntEnum):
    HEAL_CORE = auto()
    HEAL_INFRA = auto()
    ROAD_HARVESTERS = auto()
    RUSH = auto()
    CONNECT_BACK = auto()
    HARVEST_TI = auto()
    SCOUT_ENEMY = auto()
    EXPLORE = auto()
    PATROL = auto()
