from enum import IntEnum, auto


class Task(IntEnum):
    HEAL_CORE = auto()
    CUT_FEED = auto()
    DEFEND = auto()
    HARVEST = auto()  # includes greedy connect-back
    SIEGE = auto()
    EXPLORE = auto()
