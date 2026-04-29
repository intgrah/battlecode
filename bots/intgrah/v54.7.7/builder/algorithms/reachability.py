"""Incremental reachability via union-find.

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

from typing import TYPE_CHECKING

from cambc import Environment
from util.constants import MAX_WIDTH

if TYPE_CHECKING:
    from builder import Builder


K_PER_TURN: int = 25
"""Hard cap on frontier pops per turn."""

# 8-connected neighbour offsets in flat index space.
_DELTAS: tuple[int, ...] = (
    -MAX_WIDTH - 1,
    -MAX_WIDTH,
    -MAX_WIDTH + 1,
    -1,
    1,
    MAX_WIDTH - 1,
    MAX_WIDTH,
    MAX_WIDTH + 1,
)


def find(parent: list[int], i: int) -> int:
    """Find with path-halving. parent[i] must be != -1."""
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


def union(parent: list[int], a: int, b: int) -> None:
    """Union by minimum id (stable component ids)."""
    ra = find(parent, a)
    rb = find(parent, b)
    if ra == rb:
        return
    if ra < rb:
        parent[rb] = ra
    else:
        parent[ra] = rb


def step_reachability(self: Builder) -> None:
    """Pop up to K tiles from the frontier and expand 8-connected.

    Neighbour rules:
    - off-map / out of W*H interior: skip
    - parent[n] != -1 (already admitted): union with current
    - env[n] is non-WALL and known: admit n into current component, push
    - otherwise (env unknown or env == WALL): skip
    """
    parent = self.reach_parent
    frontier = self.reach_frontier
    env = self.env
    w = self.w
    h = self.h
    for _ in range(K_PER_TURN):
        if not frontier:
            return
        i = frontier.pop()
        cur_root = find(parent, i)
        cy, cx = divmod(i, MAX_WIDTH)
        for d in _DELTAS:
            n = i + d
            if n < 0 or n >= len(parent):
                continue
            ny, nx = divmod(n, MAX_WIDTH)
            if abs(ny - cy) > 1 or abs(nx - cx) > 1:
                continue
            if nx >= w or ny >= h:
                continue
            if parent[n] != -1:
                # Already admitted — union components.
                nr = find(parent, n)
                if nr != cur_root:
                    if nr < cur_root:
                        parent[cur_root] = nr
                        cur_root = nr
                    else:
                        parent[nr] = cur_root
                continue
            e = env[n]
            if e is None or e == Environment.WALL:
                continue
            parent[n] = cur_root
            frontier.append(n)


def update_reachability(self: Builder) -> None:
    """Per-turn entry point. Building admissions happen at vision time
    (see `_add_topology`); this just drains the frontier within budget.
    """
    step_reachability(self)
