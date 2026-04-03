from enum import Enum, auto
from typing import Final


class OpeningMode(Enum):
    OFF = auto()
    OPENING_ONLY = auto()
    OPENING_AND_FALLBACK = auto()


class NavMode(Enum):
    ASTAR_BUCKET = auto()
    ASTAR_LANDMARKS = auto()
    ASTAR_APSP = auto()
    BFS = auto()


OPENING: Final[OpeningMode] = OpeningMode.OFF
NAV: Final[NavMode] = NavMode.BFS
USE_HARDCODED_MAPS: Final[bool] = True
DEBUG_DUMP: Final[bool] = False
