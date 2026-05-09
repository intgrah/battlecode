from __future__ import annotations

from typing import TYPE_CHECKING, Final

from cambc import Environment, Position

if TYPE_CHECKING:
    from map26 import Map26

# 8-connected king moves (N, NE, E, SE, S, SW, W, NW).
_NEIGHBOURS: Final = (
    (0, -1),
    (1, -1),
    (1, 0),
    (1, 1),
    (0, 1),
    (-1, 1),
    (-1, 0),
    (-1, -1),
)
UNREACHABLE: Final = 0xFF


def pnb(m: Map26) -> list[tuple[int, ...]]:
    """
    Precomputed adjacency list. `adj[y*w + x]` is a tuple of cell indices
    (= ny*w + nx) of all 8-connected passable neighbours of (x, y).
    Impassable cells get an empty tuple.
    """
    w, h = m.width, m.height
    n = w * h

    passable = bytearray(n)
    for y in range(h):
        for x in range(w):
            passable[y * w + x] = 0 if m.tile(x, y) is Environment.WALL else 1

    pnb: list[tuple[int, ...]] = [()] * n
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if not passable[i]:
                continue
            ns: list[int] = []
            for dx, dy in _NEIGHBOURS:
                nx = x + dx
                ny = y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    ni = ny * w + nx
                    if passable[ni]:
                        ns.append(ni)
            pnb[i] = tuple(ns)
    return pnb


def apsp(m: Map26, pnb: list[tuple[int, ...]]) -> list[bytearray]:
    """
    All-pairs shortest paths on the map's bot-passable graph (8-connected).

    Returns a list indexed by source cell index (y*w + x); each entry is a
    bytearray of length w*h holding distances to every cell. Unreachable
    cells are `UNREACHABLE` (0xFF); impassable sources hold an empty
    bytearray. Distances cap at 254.
    """
    w, h = m.width, m.height
    n = w * h

    dist: list[bytearray] = [bytearray() for _ in range(n)]
    for si in range(n):
        if not pnb[si]:
            continue
        d = bytearray([UNREACHABLE] * n)
        d[si] = 0
        frontier = [si]
        level = 0
        while frontier:
            level += 1
            if level == UNREACHABLE:
                break
            next_frontier: list[int] = []
            for i in frontier:
                for ni in pnb[i]:
                    if d[ni] == UNREACHABLE:
                        d[ni] = level
                        next_frontier.append(ni)
            frontier = next_frontier
        dist[si] = d
    return dist


def distance(
    dist: list[bytearray],
    w: int,
    src: tuple[int, int],
    dst: tuple[int, int],
) -> int | None:
    """Look up a precomputed distance from `src` to `dst`. None if unreachable."""
    sx, sy = src
    tx, ty = dst
    d = dist[sy * w + sx]
    if not d:
        return None
    v = d[ty * w + tx]
    return None if v == UNREACHABLE else v


def extract_path(
    dist: list[bytearray],
    pnb: list[tuple[int, ...]],
    w: int,
    src: tuple[int, int],
    dst: tuple[int, int],
) -> list[Position]:
    """Reconstruct a shortest path from `src` to `dst` using APSP output.

    Returns the sequence of `Position`s including both endpoints. Returns an
    empty list if either endpoint is impassable or `dst` is unreachable.
    """
    sx, sy = src
    tx, ty = dst
    si = sy * w + sx
    ti = ty * w + tx
    d = dist[si]
    if not d or d[ti] == UNREACHABLE:
        return []
    idxs = [ti]
    cur = ti
    cur_d = d[ti]
    while cur_d > 0:
        for nb in pnb[cur]:
            if d[nb] == cur_d - 1:
                cur = nb
                cur_d -= 1
                idxs.append(cur)
                break
        else:
            return []
    idxs.reverse()
    return [Position(i % w, i // w) for i in idxs]
