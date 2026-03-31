from enum import Enum, auto
from typing import Final


class OpeningMode(Enum):
    OFF = auto()
    OPENING_ONLY = auto()
    OPENING_AND_FALLBACK = auto()


class NavMode(Enum):
    ASTAR_BUCKET_C = auto()
    ASTAR_BUCKET_PYTHON = auto()
    ASTAR_LANDMARKS = auto()
    ASTAR_APSP = auto()
    BFS = auto()
    HPA = auto()


OPENING: Final[OpeningMode] = OpeningMode.OFF
NAV: Final[NavMode] = NavMode.BFS
USE_HARDCODED_MAPS: Final[bool] = False
DEBUG_DUMP: Final[bool] = False
