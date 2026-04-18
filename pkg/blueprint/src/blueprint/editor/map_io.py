from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING

from proto import cambc_pb2

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["MapData", "Tile", "load_map"]


class Tile(IntEnum):
    EMPTY = 0
    WALL = 1
    ORE_TITANIUM = 2
    ORE_AXIONITE = 3


@dataclass(frozen=True, slots=True)
class MapData:
    name: str
    w: int
    h: int
    core_a: tuple[int, int]
    core_b: tuple[int, int]
    tiles: tuple[Tile, ...]
    """Row-major: tiles[y * w + x]."""

    def tile(self, x: int, y: int) -> Tile:
        return self.tiles[y * self.w + x]


def load_map(path: Path) -> MapData:
    m = cambc_pb2.Map()
    m.ParseFromString(path.read_bytes())
    w, h = m.width, m.height
    tiles: list[Tile] = []
    for row in m.rows:
        tiles.extend(Tile(t) for t in row.tiles)
    core_a = core_b = None
    for c in m.cores:
        pos = (c.position.x, c.position.y)
        if c.team == 0:
            core_a = pos
        else:
            core_b = pos
    if core_a is None or core_b is None:
        msg = f"Map {path} missing core A or B"
        raise ValueError(msg)
    return MapData(
        name=path.stem,
        w=w,
        h=h,
        core_a=core_a,
        core_b=core_b,
        tiles=tuple(tiles),
    )
