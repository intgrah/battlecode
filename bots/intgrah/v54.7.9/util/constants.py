from typing import Final

from cambc import EntityType, GameConstants, Position

__all__ = [
    "BASE_COST",
    "FLOW_HISTORY_LEN",
    "IDX_TO_POS",
    "INF",
    "MAX_N",
    "MAX_WIDTH",
    "ROAD_COST",
]

FLOW_HISTORY_LEN: Final = 8
"""Length of per-tile `flow_history` deques. Each entry is one observation
of the tile's stored resource (or None). Flow/volume metrics divide counts
by this constant to normalise to [0, 1]."""

INF: Final = 1_000_000
"""Large number used to represent unreachable distances or hard preferences."""

ROAD_COST: Final = 3
"""The cost of having to place a road on an empty tile, used for A* navigation."""

MAX_WIDTH: Final = 50
"""Hardcoded map-size stride for flat indexing. All flat arrays are length N."""
MAX_N: Final = MAX_WIDTH * MAX_WIDTH
"""Length of all flat per-tile arrays (2500)."""

IDX_TO_POS: Final[tuple[Position, ...]] = tuple(
    Position(i % MAX_WIDTH, i // MAX_WIDTH) for i in range(MAX_N)
)

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
