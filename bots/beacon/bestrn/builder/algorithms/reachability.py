"""
Translation of `bots/intgrah/v54.7.9/builder/algorithms/reachability.py`.

Incremental reachability via union-find.

`parent[i] == -1`  : tile i has not been admitted (no evidence it is
                     part of a reachable component).
`parent[i] == i`   : tile i is a component root.
`parent[i] != -1`  : tile i is admitted; follow parent pointers to the
                     root.

Two admission triggers:
1. **Seed**: when a building is observed on a tile (any team), the tile
   is admitted as a singleton component (parent[i] = i) and pushed to
   the frontier. The building proves the tile is reachable through
   *some* path (possibly outside our vision).
2. **Flood**: when we pop a tile from the frontier and examine its
   8-connected neighbours, any neighbour with known non-WALL env is
   admitted into the popper's component and pushed to the frontier.

The frontier persists across turns. We pop up to `K_PER_TURN` tiles per
turn. This bounds the per-turn cost without giving up eventual
completeness.

Note that "reachable" here is map-property reachability — barriers are
considered reachable, since they sit on non-WALL tiles that something
walked onto to place them.
"""

from __future__ import annotations

from typing import Final

from cambc import Environment

K_PER_TURN: Final[int] = 25
"""Hard cap on frontier pops per turn."""
DELTAS: Final[list[int]] = [
    -50 - 1,
    -50,
    -50 + 1,
    -1,
    1,
    50 - 1,
    50,
    50 + 1,
]
"""8-connected neighbour offsets in flat index space."""


def find(parent, i):
    """Find with path-halving. `parent[i]` must be `!= -1`."""
    while parent[int(i)] != i:
        p = parent[int(i)]
        parent[int(i)] = parent[int(p)]
        i = parent[int(i)]
    return i


def find_ro(parent, i):
    """
    Read-only find without path-halving. Walks the parent chain.
    `parent[i]` must be `!= -1`.
    """
    while parent[int(i)] != i:
        i = parent[int(i)]
    return i


def union(parent, a, b) -> None:
    """Union by minimum id (stable component ids)."""
    ra = find(parent, a)
    rb = find(parent, b)
    if ra == rb:
        return
    if ra < rb:
        parent[int(rb)] = ra
    else:
        parent[int(ra)] = rb


def step_reachability(parent, frontier, env, w, h) -> None:
    """
    Pop up to K tiles from the frontier and expand 8-connected.

    Neighbour rules:
    - off-map / out of W*H interior: skip
    - parent[n] != -1 (already admitted): union with current
    - env[n] is non-WALL and known: admit n into current component, push
    - otherwise (env unknown or env == WALL): skip
    """
    stride = 50
    parent_len = len(parent)
    for _ in range(25):
        i = frontier.pop() if frontier else None
        if i is None:
            return
        cur_root = find(parent, i)
        cy = i // stride
        cx = i % stride
        for d in DELTAS:
            n = i + d
            if n < 0 or n >= parent_len:
                continue
            ny = n // stride
            nx = n % stride
            if abs(ny - cy) > 1 or abs(nx - cx) > 1:
                continue
            if nx >= w or ny >= h:
                continue
            if parent[int(n)] != -1:
                nr = find(parent, n)
                if nr != cur_root:
                    if nr < cur_root:
                        parent[int(cur_root)] = nr
                        cur_root = nr
                    else:
                        parent[int(nr)] = cur_root
                continue
            e = env[int(n)]
            if (e is None) or e == Environment.WALL:
                continue
            parent[int(n)] = cur_root
            frontier.append(n)


def update_reachability(parent, frontier, env, w, h) -> None:
    """
    Per-turn entry point. Building admissions happen at vision time
    (see `_add_topology`); this just drains the frontier within budget.
    """
    step_reachability(parent, frontier, env, w, h)
