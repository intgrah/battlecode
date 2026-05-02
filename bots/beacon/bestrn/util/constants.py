"""Translation of `bots/intgrah/v54.7.9/util/constants.py`."""
from __future__ import annotations

from typing import Final

from cambc import EntityType, GameConstants
FLOW_HISTORY_LEN: Final[int] = 8
"""
Length of per-tile `flow_history` deques. Each entry is one observation
of the tile's stored resource (or `None`). Flow/volume metrics divide
counts by this constant to normalise to `[0, 1]`.
"""
INF: Final[int] = 1000000
"""Large number used to represent unreachable distances or hard preferences."""
ROAD_COST: Final[int] = 3
"""The cost of having to place a road on an empty tile, used for A* navigation."""
MAX_WIDTH: Final[int] = 50
"""Hardcoded map-size stride for flat indexing. All flat arrays are length `MAX_N`."""
MAX_N: Final[int] = 50 * 50
"""Length of all flat per-tile arrays (2500)."""

def base_cost(et):
    """
    Base `(titanium, refined_axionite)` cost for each entity type, before
    scaling. Mirrors Python `BASE_COST: dict[EntityType, tuple[int, int]]`.

    Implemented as a function rather than a `HashMap` so it's `const`-friendly
    and allocation-free. Returns `None` for entity types that aren't placeable
    buildings (CORE, MARKER, BUILDER_BOT-on-spawn handled separately).
    """
    match et:
        case EntityType.BUILDER_BOT:
            return GameConstants.BUILDER_BOT_BASE_COST
        case EntityType.HARVESTER:
            return GameConstants.HARVESTER_BASE_COST
        case EntityType.SENTINEL:
            return GameConstants.SENTINEL_BASE_COST
        case EntityType.GUNNER:
            return GameConstants.GUNNER_BASE_COST
        case EntityType.LAUNCHER:
            return GameConstants.LAUNCHER_BASE_COST
        case EntityType.CONVEYOR:
            return GameConstants.CONVEYOR_BASE_COST
        case EntityType.BRIDGE:
            return GameConstants.BRIDGE_BASE_COST
        case EntityType.SPLITTER:
            return GameConstants.SPLITTER_BASE_COST
        case EntityType.BARRIER:
            return GameConstants.BARRIER_BASE_COST
        case EntityType.ROAD:
            return GameConstants.ROAD_BASE_COST
        case EntityType.FOUNDRY:
            return GameConstants.FOUNDRY_BASE_COST
        case EntityType.BREACH:
            return GameConstants.BREACH_BASE_COST
        case _:
            return None
