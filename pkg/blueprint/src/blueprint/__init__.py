"""Blueprint client library.

The Python module a bot imports (via a symlink inside the bot's source tree,
mirroring the `visualiser` package pattern) to get the `BlueprintEntry` type
and helpers for executing a hardcoded blueprint at runtime.

The editor GUI lives in `blueprint.editor` and is not needed at bot runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

__all__ = [
    "DELTA_DIR",
    "DIRECTIONAL",
    "DIR_DELTA",
    "TURRET",
    "BlueprintEntry",
    "Direction",
    "Entity",
    "mirror_delta",
    "mirror_entry",
    "mirror_pos",
]


class Entity(IntEnum):
    """Placeable entity kinds. Values match `cambc.EntityType`."""

    CONVEYOR = 4
    SPLITTER = 5
    ARMOURED_CONVEYOR = 6
    BRIDGE = 7
    HARVESTER = 8
    FOUNDRY = 9
    GUNNER = 10
    SENTINEL = 11
    BREACH = 13
    LAUNCHER = 12
    BARRIER = 14
    ROAD = 15


class Direction(IntEnum):
    """8-way directions. Values match `cambc.Direction`."""

    NORTH = 1
    NORTHEAST = 2
    EAST = 3
    SOUTHEAST = 4
    SOUTH = 5
    SOUTHWEST = 6
    WEST = 7
    NORTHWEST = 8


DIR_DELTA: dict[Direction, tuple[int, int]] = {
    Direction.NORTH: (0, -1),
    Direction.NORTHEAST: (1, -1),
    Direction.EAST: (1, 0),
    Direction.SOUTHEAST: (1, 1),
    Direction.SOUTH: (0, 1),
    Direction.SOUTHWEST: (-1, 1),
    Direction.WEST: (-1, 0),
    Direction.NORTHWEST: (-1, -1),
}

DELTA_DIR: dict[tuple[int, int], Direction] = {d: k for k, d in DIR_DELTA.items()}

DIRECTIONAL: frozenset[Entity] = frozenset(
    {
        Entity.CONVEYOR,
        Entity.SPLITTER,
        Entity.ARMOURED_CONVEYOR,
        Entity.GUNNER,
        Entity.SENTINEL,
        Entity.BREACH,
    },
)

TURRET: frozenset[Entity] = frozenset(
    {Entity.GUNNER, Entity.SENTINEL, Entity.BREACH, Entity.LAUNCHER},
)


@dataclass(frozen=True, slots=True)
class BlueprintEntry:
    """One action in a pre-authored blueprint.

    Blueprints are written P1-side-only; the runtime mirrors on the fly
    via `mirror_entry` given the map's symmetry.
    """

    pos: tuple[int, int]
    kind: Entity
    direction: Direction | None = None
    bridge_target: tuple[int, int] | None = None


def mirror_pos(
    pos: tuple[int, int],
    w: int,
    h: int,
    sym: str,
) -> tuple[int, int]:
    """Reflect a position under the map's symmetry ('hor' | 'ver' | 'rot')."""
    x, y = pos
    if sym == "hor":
        return (x, h - 1 - y)
    if sym == "ver":
        return (w - 1 - x, y)
    if sym == "rot":
        return (w - 1 - x, h - 1 - y)
    msg = f"unknown symmetry: {sym!r}"
    raise ValueError(msg)


def mirror_delta(dx: int, dy: int, sym: str) -> tuple[int, int]:
    """Reflect a direction delta under the map's symmetry."""
    if sym == "hor":
        return (dx, -dy)
    if sym == "ver":
        return (-dx, dy)
    if sym == "rot":
        return (-dx, -dy)
    msg = f"unknown symmetry: {sym!r}"
    raise ValueError(msg)


def mirror_entry(entry: BlueprintEntry, w: int, h: int, sym: str) -> BlueprintEntry:
    """Return the entry reflected to the other half of the map."""
    direction = entry.direction
    if direction is not None:
        dx, dy = DIR_DELTA[direction]
        direction = DELTA_DIR.get(mirror_delta(dx, dy, sym), direction)
    bt = entry.bridge_target
    if bt is not None:
        bt = mirror_pos(bt, w, h, sym)
    return BlueprintEntry(
        pos=mirror_pos(entry.pos, w, h, sym),
        kind=entry.kind,
        direction=direction,
        bridge_target=bt,
    )
