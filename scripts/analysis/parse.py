from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .types import MapMeta

if TYPE_CHECKING:
    from proto.cambc_pb2 import Replay


def parse(path: str) -> Replay:
    from proto.cambc_pb2 import Replay as _Replay

    with Path(path).open("rb") as f:
        r = _Replay()
        r.ParseFromString(f.read())
        return r


def extract_map_meta(replay: Replay) -> MapMeta:
    m = replay.map
    w, h = m.width, m.height

    core_pos: dict[int, tuple[int, int]] = {}
    for c in m.cores:
        core_pos[c.team] = (c.position.x, c.position.y)

    ore_tiles: list[tuple[int, int, str]] = []
    for y, row in enumerate(m.rows):
        for x, t in enumerate(row.tiles):
            if t == 2:
                ore_tiles.append((x, y, "titanium"))
            elif t == 3:
                ore_tiles.append((x, y, "axionite"))

    passable = sum(1 for y in range(h) for x in range(w) if m.rows[y].tiles[x] != 1)

    return MapMeta(
        width=w,
        height=h,
        core_pos=core_pos,
        ore_tiles=ore_tiles,
        passable_count=passable,
    )
