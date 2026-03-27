import base64
import sys
import zlib
from collections import deque
from pathlib import Path

from cambc import Environment, Position

from .known import KnownMap
from .map import MAPS, decode

_KEY_TO_ATTR: dict[tuple[int, int, Position], str] = {
    getattr(KnownMap, attr): attr for attr in dir(KnownMap) if not attr.startswith("_")
}


def _determine_symmetry(w: int, h: int, core_a: Position, core_b: Position) -> str:
    ax, ay = core_a.x, core_a.y
    bx, by = core_b.x, core_b.y
    if ax == bx and ay + by == h - 1:
        return "HOR"
    if ay == by and ax + bx == w - 1:
        return "VER"
    return "ROT"


def _mirror_index(i: int, w: int, h: int, sym: str) -> int:
    x, y = i % w, i // w
    match sym:
        case "ROT":
            return (h - 1 - y) * w + (w - 1 - x)
        case "HOR":
            return (h - 1 - y) * w + x
        case "VER":
            return y * w + (w - 1 - x)
    return i


def _is_stored_half(i: int, w: int, h: int, sym: str) -> bool:
    return i <= _mirror_index(i, w, h, sym)


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
) -> tuple[bytes, list[int]]:
    n = w * h
    passable = bytearray(n)
    for i in range(n):
        passable[i] = env[i] != Environment.WALL
    neighbors = _build_neighbors(w, h)

    stored_indices = [i for i in range(n) if _is_stored_half(i, w, h, sym)]

    rows = bytearray()
    for i in stored_indices:
        if passable[i]:
            rows.extend(_bfs(n, passable, neighbors, i))
        else:
            rows.extend(b"\xff" * n)
    return bytes(rows), stored_indices


def main() -> None:
    out = Path(__file__).parent / "apsp.py"
    line_len = 100

    with out.open("w") as f:
        f.write("from util import Symmetry\n\n")
        f.write("from .known import KnownMap, MapKey\n\n")
        f.write(
            "APSP: dict[MapKey, tuple[Symmetry, str, str]] = {\n",
        )

        for key, (encoded, core_b) in MAPS.items():
            w, h, core_a = key
            attr = _KEY_TO_ATTR.get(key)
            name = attr.lower() if attr else f"{w}x{h}"
            n = w * h
            env = decode(encoded, n)
            sym = _determine_symmetry(w, h, core_a, core_b)

            print(f"  {name} ({w}x{h})...", end=" ", flush=True, file=sys.stderr)
            raw, stored_indices = _compute_half_apsp(w, h, env, sym)
            compressed = zlib.compress(raw, 9)
            b64 = base64.b64encode(compressed).decode("ascii")
            print(f"zlib={len(compressed)}, b64={len(b64)}", file=sys.stderr)

            f.write(f"    # {name}\n")
            if attr:
                f.write(f"    KnownMap.{attr}: (\n")
            else:
                f.write(f"    ({w}, {h}, Position({core_a.x}, {core_a.y})): (\n")
            f.write(f"        Symmetry.{sym},\n")

            lines = [b64[i : i + line_len] for i in range(0, len(b64), line_len)]
            f.write('        "')
            f.write('"\n        "'.join(lines))
            f.write('",\n')

            stored_raw = b"".join(idx.to_bytes(2, "little") for idx in stored_indices)
            stored_compressed = zlib.compress(stored_raw, 9)
            stored_b64 = base64.b64encode(stored_compressed).decode("ascii")
            stored_lines = [
                stored_b64[i : i + line_len]
                for i in range(0, len(stored_b64), line_len)
            ]
            f.write('        "')
            f.write('"\n        "'.join(stored_lines))
            f.write('",\n')

            f.write("    ),\n")

        f.write("}\n")

    print(f"Wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
