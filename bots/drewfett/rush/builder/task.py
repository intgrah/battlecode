from enum import IntEnum, auto


class Task(IntEnum):
    HEAL_CORE = auto()
    HEAL_INFRA = auto()
    SIEGE = auto()
    CONNECT_BACK = auto()
    HARVEST_TI = auto()
    EXPLORE = auto()
    DEFEND = auto()
    CUT_FEED = auto()
