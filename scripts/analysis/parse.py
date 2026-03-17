from __future__ import annotations

from pathlib import Path

from .types import MapMeta

_proto_path_added = False


def _ensure_proto_path() -> None:
    global _proto_path_added  # noqa: PLW0603
    if not _proto_path_added:
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "proto"))
        _proto_path_added = True


def parse(path: str) -> object:
    _ensure_proto_path()
    from cambc_pb2 import Replay  # type: ignore[import-not-found]

    with Path(path).open("rb") as f:
        r = Replay()
        r.ParseFromString(f.read())
        return r


def extract_map_meta(replay: object) -> MapMeta:
    m = replay.map  # type: ignore[attr-defined]
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
