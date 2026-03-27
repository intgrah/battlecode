import sys
from collections import deque
from pathlib import Path

from cambc import Environment, Position

from .known import KnownMap
from .map import MAPS, decode

_KEY_TO_ATTR: dict[tuple[int, int, Position], str] = {
    getattr(KnownMap, attr): attr for attr in dir(KnownMap) if not attr.startswith("_")
}

_BYTES_PER_LINE = 60


def _determine_symmetry(w: int, h: int, core_a: Position, core_b: Position) -> str:
    ax, ay = core_a.x, core_a.y
    bx, by = core_b.x, core_b.y
    if ax == bx and ay + by == h - 1:
        return "HOR"
    if ay == by and ax + bx == w - 1:
        return "VER"
    return "ROT"


def _stored_tiles(w: int, h: int, sym: str) -> list[int]:
    n = w * h
    half_w = (w + 1) // 2
    half_h = (h + 1) // 2
    half_n = (n + 1) // 2
    result: list[int] = []
    match sym:
        case "ROT":
            result = list(range(half_n))
        case "HOR":
            result = list(range(half_h * w))
        case "VER":
            for y in range(h):
                for x in range(half_w):
                    result.append(y * w + x)
    return result


def _bfs(
    n: int,
    passable: bytearray,
    neighbors: list[list[int]],
    start: int,
) -> bytearray:
    dist = bytearray(b"\xff" * n)
    dist[start] = 0
    q = deque([start])
    while q:
        ci = q.popleft()
        nd = dist[ci] + 1
        if nd >= 255:
            continue
        for ni in neighbors[ci]:
            if passable[ni] and dist[ni] == 0xFF:
                dist[ni] = nd
                q.append(ni)
    return dist


def _build_neighbors(w: int, h: int) -> list[list[int]]:
    n = w * h
    neighbors: list[list[int]] = []
    for i in range(n):
        cx, cy = i % w, i // w
        nb: list[int] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h:
                    nb.append(ny * w + nx)
        neighbors.append(nb)
    return neighbors


def _compute_half_apsp(
    w: int,
    h: int,
    env: list[Environment],
    sym: str,
) -> bytes:
    n = w * h
    passable = bytearray(n)
    for i in range(n):
        passable[i] = env[i] != Environment.WALL
    neighbors = _build_neighbors(w, h)

    tiles = _stored_tiles(w, h, sym)
    rows = bytearray()
    for i in tiles:
        if passable[i]:
            rows.extend(_bfs(n, passable, neighbors, i))
        else:
            rows.extend(b"\xff" * n)
    return bytes(rows)


def _bytes_literal(data: bytes) -> str:
    lines: list[str] = []
    for i in range(0, len(data), _BYTES_PER_LINE):
        chunk = data[i : i + _BYTES_PER_LINE]
        escaped = "".join(f"\\x{b:02x}" for b in chunk)
        lines.append(f'        b"{escaped}"')
    return "\n".join(lines)


def main() -> None:
    out = Path(__file__).parent / "apsp.py"

    with out.open("w") as f:
        f.write("from util import Symmetry\n\n")
        f.write("from .known import KnownMap, MapKey\n\n")
        f.write("SYMMETRY: dict[MapKey, Symmetry] = {\n")

        syms: dict[tuple[int, int, Position], str] = {}
        for key, (_, core_b) in MAPS.items():
            w, h, core_a = key
            attr = _KEY_TO_ATTR.get(key)
            sym = _determine_symmetry(w, h, core_a, core_b)
            syms[key] = sym
            if attr:
                f.write(f"    KnownMap.{attr}: Symmetry.{sym},\n")
        f.write("}\n\n")

        for key, (encoded, _) in MAPS.items():
            w, h, core_a = key
            attr = _KEY_TO_ATTR.get(key)
            if attr is None:
                continue
            name = attr.lower()
            n = w * h
            env = decode(encoded, n)
            sym = syms[key]

            tiles = _stored_tiles(w, h, sym)
            print(
                f"  {name} ({w}x{h}): {sym}, {len(tiles)} rows...",
                end=" ",
                flush=True,
                file=sys.stderr,
            )
            raw = _compute_half_apsp(w, h, env, sym)
            print(f"{len(raw)} bytes", file=sys.stderr)

            f.write(f"\n\ndef {name}() -> bytes:\n")
            f.write("    return (\n")
            f.write(_bytes_literal(raw) + "\n")
            f.write("    )\n")

    print(f"Wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
