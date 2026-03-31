import sys
import time
from collections import deque
from pathlib import Path

from cambc import Environment

from .known import KnownMap
from .map import CORE_A, CORE_B, DIMENSIONS, TILES, decode

_BYTES_PER_LINE = 60
_NUM_LANDMARKS = 8


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


def _bfs(
    n: int,
    passable: bytearray,
    neighbors: list[list[int]],
    start: int,
) -> bytearray:
    dist = bytearray(b"\xff" * n)
    dist[start] = 0
    q: deque[int] = deque([start])
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


def _pick_landmarks(
    n: int,
    passable: bytearray,
    neighbors: list[list[int]],
    core_a: int,
    core_b: int,
    k: int,
) -> list[int]:
    landmarks = [core_a, core_b]
    dists: list[bytearray] = [_bfs(n, passable, neighbors, lm) for lm in landmarks]

    while len(landmarks) < k:
        best = -1
        best_min_dist = -1
        for i in range(n):
            if not passable[i]:
                continue
            min_d = min(d[i] for d in dists)
            if min_d > best_min_dist:
                best_min_dist = min_d
                best = i
        if best < 0:
            break
        landmarks.append(best)
        dists.append(_bfs(n, passable, neighbors, best))

    return landmarks


def _compute_landmarks(
    w: int,
    h: int,
    env: list[Environment],
    core_a_idx: int,
    core_b_idx: int,
    k: int,
) -> tuple[list[int], bytes]:
    n = w * h
    passable = bytearray(n)
    for i in range(n):
        passable[i] = env[i] != Environment.WALL
    neighbors = _build_neighbors(w, h)

    landmarks = _pick_landmarks(n, passable, neighbors, core_a_idx, core_b_idx, k)

    rows = bytearray()
    for lm in landmarks:
        rows.extend(_bfs(n, passable, neighbors, lm))

    return landmarks, bytes(rows)


def _bytes_literal(data: bytes) -> str:
    lines: list[str] = []
    for i in range(0, len(data), _BYTES_PER_LINE):
        chunk = data[i : i + _BYTES_PER_LINE]
        escaped = "".join(f"\\x{b:02x}" for b in chunk)
        lines.append(f'        b"{escaped}"')
    return "\n".join(lines)


def main() -> None:
    out = Path(__file__).parent / "landmarks.py"

    with out.open("w") as f:
        f.write("from collections.abc import Callable\n\n")
        f.write("from .known import KnownMap\n\n\n")

        for km in KnownMap:
            w, h = DIMENSIONS[km]
            n = w * h
            env = decode(TILES[km](), n)
            ca, cb = CORE_A[km], CORE_B[km]
            ca_idx = ca.y * w + ca.x
            cb_idx = cb.y * w + cb.x

            t0 = time.perf_counter()
            landmarks, raw = _compute_landmarks(
                w,
                h,
                env,
                ca_idx,
                cb_idx,
                _NUM_LANDMARKS,
            )
            elapsed = time.perf_counter() - t0
            lm_coords = [(lm % w, lm // w) for lm in landmarks]
            print(
                f"  {km.value} ({w}x{h}): {len(landmarks)} landmarks,"
                f" {len(raw):,} bytes, {elapsed:.2f}s"
                f"  lm={lm_coords}",
                file=sys.stderr,
            )

            f.write(f"def _{km.value}() -> tuple[list[int], int, bytes]:\n")
            f.write("    return (\n")
            f.write(f"        {landmarks},\n")
            f.write(f"        {n},\n")
            f.write("        (\n")
            f.write(_bytes_literal(raw) + "\n")
            f.write("        ),\n")
            f.write("    )\n\n\n")

        f.write(
            "DATA: dict[KnownMap, Callable[[], tuple[list[int], int, bytes]]] = {\n",
        )
        for km in KnownMap:
            f.write(f"    KnownMap.{km.name}: _{km.value},\n")
        f.write("}\n")

    print(f"Wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
