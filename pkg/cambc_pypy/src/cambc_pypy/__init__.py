__version__ = "1.6.2-alpha"

import sys
import warnings

if sys.implementation.name != "pypy":
    warnings.warn(
        f"cambc_pypy is running under {sys.implementation.name}. Expected PyPy.",
        RuntimeWarning,
        stacklevel=1,
    )

from cambc_pypy.engine import (
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
