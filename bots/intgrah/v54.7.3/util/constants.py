from typing import Final

from cambc import EntityType, GameConstants

__all__ = ["BASE_COST", "INF", "MAX_N", "MAX_WIDTH", "ROAD_COST"]

INF: Final = 1_000_000
"""Large number used to represent unreachable distances or hard preferences."""

ROAD_COST: Final = 3
"""The cost of having to place a road on an empty tile, used for A* navigation."""

MAX_WIDTH: Final = 50
"""Hardcoded map-size stride for flat indexing. All flat arrays are length N."""
MAX_N: Final = MAX_WIDTH * MAX_WIDTH
"""Length of all flat per-tile arrays (2500)."""

BASE_COST: Final = {
    EntityType.BUILDER_BOT: GameConstants.BUILDER_BOT_BASE_COST,
    EntityType.HARVESTER: GameConstants.HARVESTER_BASE_COST,
    EntityType.SENTINEL: GameConstants.SENTINEL_BASE_COST,
    EntityType.GUNNER: GameConstants.GUNNER_BASE_COST,
    EntityType.LAUNCHER: GameConstants.LAUNCHER_BASE_COST,
    EntityType.CONVEYOR: GameConstants.CONVEYOR_BASE_COST,
    EntityType.BRIDGE: GameConstants.BRIDGE_BASE_COST,
    EntityType.SPLITTER: GameConstants.SPLITTER_BASE_COST,
    EntityType.BARRIER: GameConstants.BARRIER_BASE_COST,
    EntityType.ROAD: GameConstants.ROAD_BASE_COST,
    EntityType.FOUNDRY: GameConstants.FOUNDRY_BASE_COST,
    EntityType.BREACH: GameConstants.BREACH_BASE_COST,
}
