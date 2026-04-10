__version__ = "1.6.2"

import sys
import warnings

if sys.implementation.name != "pypy":
    warnings.warn(
        f"cambcpypy is running under {sys.implementation.name}. Expected PyPy.",
        RuntimeWarning,
        stacklevel=1,
    )

from cambcpypy.engine import (
    Controller,
    Direction,
    EntityType,
    Environment,
    GameConstants,
    GameError,
    Position,
    ResourceType,
    Team,
)

__all__ = [
    "Controller",
    "Direction",
    "EntityType",
    "Environment",
    "GameConstants",
    "GameError",
    "Position",
    "ResourceType",
    "Team",
]
