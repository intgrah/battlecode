"""Incremental reachability flood from a source position.

Tracks which tiles are reachable from a source over the environment
(walls block, everything else is passable). Buildings are ignored.

Wave expansion is suspended at any node adjacent to an unseen tile
(passable == 2). Suspended nodes are retried on the next `compute()`
call, because newly observed tiles may have unblocked them.

Internal grid is padded by 1 tile on each side (sentinel border).
"""

from __future__ import annotations

from astar import ChainAstar
from cambc import Environment, Position
from tile_codec import tile_building_type, tile_env, tile_is_allied

# 8-neighbour offsets (computed from padded width in __init__).


class Reachable:
    """Incremental 8-connected reachability from a single source."""

    def __init__(self, w: int, h: int) -> None:
        self.w = w
        self.h = h
        pw = w + 2
        self._pw = pw
        n = pw * (h + 2)
        self._n = n

        # 0 = wall/border, 1 = seen passable, 2 = unseen (treated as blocking
        # for now, but causes adjacent nodes to be suspended).
        self._passable: list[int] = [2] * n
        for x in range(pw):
            self._passable[x] = 0
            self._passable[(h + 1) * pw + x] = 0
        for y in range(1, h + 1):
            self._passable[y * pw] = 0
            self._passable[y * pw + pw - 1] = 0

        self._reachable: list[bool] = [False] * n
        self._frontier: list[int] = []
        self._source_pi: int = -1
        self._dirty = True

        self._offsets: tuple[int, ...] = (
            -pw - 1,
            -pw,
            -pw + 1,
            -1,
            1,
            pw - 1,
            pw,
            pw + 1,
        )

    def update_tile(self, i: int, env: Environment) -> None:
        """Mark a real tile index as seen and record its environment."""
        pi = i + 2 * (i // self.w) + self._pw + 1
        new = 0 if env == Environment.WALL else 1
        if self._passable[pi] != new:
            self._passable[pi] = new
            self._dirty = True

    def set_source(self, pos: Position) -> None:
        """Set (or change) the source position. Resets the flood."""
        pi = (pos.y + 1) * self._pw + (pos.x + 1)
        if pi == self._source_pi:
            return
        self._source_pi = pi
        self._reachable = [False] * self._n
        self._frontier = []
        if self._passable[pi]:
            self._reachable[pi] = True
            self._frontier.append(pi)
        self._dirty = True

    def compute(self, tile_cache: list[int], chain: ChainAstar) -> None:
        """Continue the flood. Idempotent — cheap if nothing changed."""
        if not self._dirty:
            return
        passable = self._passable
        reachable = self._reachable
        offsets = self._offsets
        w = self.w
        pw = self._pw

        q = self._frontier
        new_frontier: list[int] = []
        for node in q:
            # Suspend if any neighbour is unseen — we may learn more later.
            for off in offsets:
                if passable[node + off] == 2:
                    new_frontier.append(node)
                    break
            else:
                for off in offsets:
                    ni = node + off
                    if passable[ni] == 1 and not reachable[ni]:
                        reachable[ni] = True
                        ry = ni // pw - 1
                        rx = ni % pw - 1
                        tile = tile_cache[ry * w + rx]
                        chain.update_tile(
                            rx,
                            ry,
                            tile_env(tile),
                            tile_building_type(tile),
                            tile_is_allied(tile),
                            force_update=True,
                        )
                        q.append(ni)

        self._frontier = new_frontier
        self._dirty = False

    def is_reachable(self, pos: Position) -> bool:
        """Return True if `pos` is currently known to be reachable."""
        pi = (pos.y + 1) * self._pw + (pos.x + 1)
        return self._reachable[pi]
