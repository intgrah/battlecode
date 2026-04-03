import sys
from collections import deque
from pathlib import Path

from cambc import Environment

from .known import KnownMap
from .map import DIMENSIONS, SYMMETRY, TILES, decode

_BYTES_PER_LINE = 60


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
        f.write("from collections.abc import Callable\n\n")
        f.write("from .known import KnownMap\n\n\n")

        for km in KnownMap:
            w, h = DIMENSIONS[km]
            n = w * h
            env = decode(TILES[km](), n)
            sym = SYMMETRY[km].name

            tiles = _stored_tiles(w, h, sym)
            print(
                f"  {km.value} ({w}x{h}): {sym}, {len(tiles)} rows...",
                end=" ",
                flush=True,
                file=sys.stderr,
            )
            raw = _compute_half_apsp(w, h, env, sym)
            print(f"{len(raw)} bytes", file=sys.stderr)

            f.write(f"def _{km.value}() -> bytes:\n")
            f.write("    return (\n")
            f.write(_bytes_literal(raw) + "\n")
            f.write("    )\n\n\n")

        f.write("DATA: dict[KnownMap, Callable[[], bytes]] = {\n")
        for km in KnownMap:
            f.write(f"    KnownMap.{km.name}: _{km.value},\n")
        f.write("}\n")

    print(f"Wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
