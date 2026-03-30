from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from proto import cambc_pb2

from .known import KnownMap

if TYPE_CHECKING:
    from collections.abc import Callable

_MAPS_DIR = Path(__file__).resolve().parents[4] / "maps"
_BYTES_PER_LINE = 60


def _determine_symmetry(
    w: int,
    h: int,
    tiles: list[int],
) -> str:
    def _check(transform: Callable[[int, int], tuple[int, int]]) -> bool:
        for y in range(h):
            for x in range(w):
                mx, my = transform(x, y)
                if tiles[y * w + x] != tiles[my * w + mx]:
                    return False
        return True

    if _check(lambda x, y: (x, h - 1 - y)):
        return "HOR"
    if _check(lambda x, y: (w - 1 - x, y)):
        return "VER"
    if _check(lambda x, y: (w - 1 - x, h - 1 - y)):
        return "ROT"
    msg = "no symmetry detected"
    raise ValueError(msg)


def _pack_tiles(tiles: list[int]) -> bytes:
    packed = bytearray()
    for i in range(0, len(tiles), 4):
        b = 0
        for j in range(4):
            if i + j < len(tiles):
                b |= (tiles[i + j] & 3) << (j * 2)
        packed.append(b)
    return bytes(packed)


def _bytes_literal(data: bytes) -> str:
    lines: list[str] = []
    for i in range(0, len(data), _BYTES_PER_LINE):
        chunk = data[i : i + _BYTES_PER_LINE]
        escaped = "".join(f"\\x{b:02x}" for b in chunk)
        lines.append(f'        b"{escaped}"')
    return "\n".join(lines)


def _parse_map(name: str) -> tuple[int, int, int, int, int, int, list[int]]:
    path = _MAPS_DIR / f"{name}.map26"
    m = cambc_pb2.Map()
    m.ParseFromString(path.read_bytes())
    w, h = m.width, m.height
    tiles: list[int] = []
    for row in m.rows:
        tiles.extend(row.tiles)
    core_a = core_b = None
    for c in m.cores:
        if c.team == 0:
            core_a = (c.position.x, c.position.y)
        else:
            core_b = (c.position.x, c.position.y)
    assert core_a is not None
    assert core_b is not None
    return w, h, core_a[0], core_a[1], core_b[0], core_b[1], tiles


def main() -> None:
    out = Path(__file__).with_name("map.py")

    entries: list[tuple[KnownMap, int, int, int, int, int, int, str, bytes]] = []
    for km in KnownMap:
        w, h, ax, ay, bx, by, tiles = _parse_map(km.value)
        sym = _determine_symmetry(w, h, tiles)
        packed = _pack_tiles(tiles)
        entries.append((km, w, h, ax, ay, bx, by, sym, packed))

    with out.open("w") as f:
        f.write("from collections.abc import Callable\n\n")
        f.write("from cambc import Environment, Position\n")
        f.write("from util import Symmetry\n\n")
        f.write("from .known import KnownMap\n\n")

        f.write("DIMENSIONS: dict[KnownMap, tuple[int, int]] = {\n")
        for km, w, h, _, _, _, _, _, _ in entries:
            f.write(f"    KnownMap.{km.name}: ({w}, {h}),\n")
        f.write("}\n\n")

        f.write("CORE_A: dict[KnownMap, Position] = {\n")
        for km, _, _, ax, ay, _, _, _, _ in entries:
            f.write(f"    KnownMap.{km.name}: Position({ax}, {ay}),\n")
        f.write("}\n\n")

        f.write("CORE_B: dict[KnownMap, Position] = {\n")
        for km, _, _, _, _, bx, by, _, _ in entries:
            f.write(f"    KnownMap.{km.name}: Position({bx}, {by}),\n")
        f.write("}\n\n")

        f.write("SYMMETRY: dict[KnownMap, Symmetry] = {\n")
        for km, _, _, _, _, _, _, sym, _ in entries:
            f.write(f"    KnownMap.{km.name}: Symmetry.{sym},\n")
        f.write("}\n\n")

        f.write("_TILE_TO_ENV: tuple[Environment, ...] = (\n")
        f.write("    Environment.EMPTY,\n")
        f.write("    Environment.WALL,\n")
        f.write("    Environment.ORE_TITANIUM,\n")
        f.write("    Environment.ORE_AXIONITE,\n")
        f.write(")\n\n\n")

        f.write("def decode(data: bytes, n: int) -> list[Environment]:\n")
        f.write("    tiles: list[Environment] = []\n")
        f.write("    for b in data:\n")
        f.write("        for j in range(4):\n")
        f.write("            if len(tiles) >= n:\n")
        f.write("                break\n")
        f.write("            tiles.append(_TILE_TO_ENV[(b >> (j * 2)) & 3])\n")
        f.write("    return tiles\n\n\n")

        f.write("CANDIDATES: dict[tuple[int, int, Position], list[KnownMap]] = {}\n")
        f.write("for _km in KnownMap:\n")
        f.write("    _key = (*DIMENSIONS[_km], CORE_A[_km])\n")
        f.write("    CANDIDATES.setdefault(_key, []).append(_km)\n")

        for km, _, _, _, _, _, _, _, packed in entries:
            f.write(f"def _{km.value}() -> bytes:\n")
            f.write("    return (\n")
            f.write(_bytes_literal(packed) + "\n")
            f.write("    )\n\n\n")

        f.write("TILES: dict[KnownMap, Callable[[], bytes]] = {\n")
        for km, _, _, _, _, _, _, _, _ in entries:
            f.write(f"    KnownMap.{km.name}: _{km.value},\n")
        f.write("}\n")

    print(f"Wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
