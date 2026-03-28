from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Direction

if TYPE_CHECKING:
    from .types import OpeningBuilderTurn


def wait(n: int) -> list[OpeningBuilderTurn]:
    return [(None, None)] * n


n: OpeningBuilderTurn = (None, Direction.NORTH)
ne: OpeningBuilderTurn = (None, Direction.NORTHEAST)
e: OpeningBuilderTurn = (None, Direction.EAST)
se: OpeningBuilderTurn = (None, Direction.SOUTHEAST)
s: OpeningBuilderTurn = (None, Direction.SOUTH)
sw: OpeningBuilderTurn = (None, Direction.SOUTHWEST)
w: OpeningBuilderTurn = (None, Direction.WEST)
nw: OpeningBuilderTurn = (None, Direction.NORTHWEST)

n: OpeningBuilderTurn = (None, Direction.NORTH)
ne: OpeningBuilderTurn = (None, Direction.NORTHEAST)
e: OpeningBuilderTurn = (None, Direction.EAST)
se: OpeningBuilderTurn = (None, Direction.SOUTHEAST)
s: OpeningBuilderTurn = (None, Direction.SOUTH)
sw: OpeningBuilderTurn = (None, Direction.SOUTHWEST)
w: OpeningBuilderTurn = (None, Direction.WEST)
nw: OpeningBuilderTurn = (None, Direction.NORTHWEST)
