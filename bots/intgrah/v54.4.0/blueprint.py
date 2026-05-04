"""Blueprint client library — GENERATED from titan-blueprint.

Do not edit by hand. Regenerate with:
    cargo run -p titan-blueprint --bin gen-blueprint-py -- <out.py>
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
    CONVEYOR = 4
    ARMOURED_CONVEYOR = 6
    SPLITTER = 5
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

DIRECTIONAL: frozenset[Entity] = frozenset({
    Entity.CONVEYOR,
    Entity.ARMOURED_CONVEYOR,
    Entity.SPLITTER,
    Entity.GUNNER,
    Entity.SENTINEL,
    Entity.BREACH,
})

TURRET: frozenset[Entity] = frozenset({
    Entity.GUNNER,
    Entity.SENTINEL,
    Entity.BREACH,
    Entity.LAUNCHER,
})

DELTA_DIR: dict[tuple[int, int], Direction] = {d: k for k, d in DIR_DELTA.items()}


@dataclass(frozen=True, slots=True)
class BlueprintEntry:
    pos: tuple[int, int]
    kind: Entity
    phase: int
    direction: Direction | None = None
    bridge_target: tuple[int, int] | None = None


def mirror_pos(pos: tuple[int, int], w: int, h: int, sym: str) -> tuple[int, int]:
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
    if sym == "hor":
        return (dx, -dy)
    if sym == "ver":
        return (-dx, dy)
    if sym == "rot":
        return (-dx, -dy)
    msg = f"unknown symmetry: {sym!r}"
    raise ValueError(msg)


def mirror_entry(entry: BlueprintEntry, w: int, h: int, sym: str) -> BlueprintEntry:
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
        phase=entry.phase,
        direction=direction,
        bridge_target=bt,
    )
