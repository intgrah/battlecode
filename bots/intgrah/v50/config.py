from enum import Enum, auto
from typing import Final

INF: Final[int] = 1_000_000

COST_ROAD: Final[int] = 2
COST_EMPTY: Final[int] = 10
COST_UNSEEN: Final[int] = 12
COST_IMPASSABLE: Final[int] = INF


class OpeningMode(Enum):
    OFF = auto()
    OPENING_ONLY = auto()
    OPENING_AND_FALLBACK = auto()


OPENING: Final[OpeningMode] = OpeningMode.OFF
USE_HARDCODED_MAPS: Final[bool] = True
USE_APSP: Final[bool] = False
DEBUG_DUMP: Final[bool] = False
