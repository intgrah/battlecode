"""Incremental reachability flood from a source position.

Tracks which tiles are reachable from a source over the environment
(walls block, everything else is passable). Buildings are ignored.

Wave expansion is suspended at any node adjacent to an unseen tile
(passable == 2). Suspended nodes are retried on the next `compute()`
call, because newly observed tiles may have unblocked them.

Internal grid is padded by 1 tile on each side (sentinel border).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Environment, Position
from lib.visualiser.src.visualiser import Grid, Palette, emit
from symmetry import Symmetry, mirror_idx
from tile_codec import tile_building_type, tile_env, tile_is_allied

if TYPE_CHECKING:
    from astar import ChainAstar

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

    def update_tile(
        self,
        i: int,
        env: Environment,
        sym: Symmetry = Symmetry.UNKNOWN,
    ) -> None:
        """Mark a real tile index as seen and record its environment.

        When `sym` is resolved, also write the mirrored tile's passability
        — but only if that mirror tile has not already been directly
        observed (i.e. is still `2`). Direct observations beat inferences.
        """
        pi = i + 2 * (i // self.w) + self._pw + 1
        new = 0 if env == Environment.WALL else 1
        if self._passable[pi] != new:
            self._passable[pi] = new
            self._dirty = True

        if sym is not Symmetry.UNKNOWN:
            mi = mirror_idx(i, sym, self.w, self.h)
            mpi = mi + 2 * (mi // self.w) + self._pw + 1
            if self._passable[mpi] == 2:
                self._passable[mpi] = new
                self._dirty = True

    def mirror_known(self, sym: Symmetry, known_env: dict[int, Environment]) -> None:
        """Bulk-mirror all previously observed tile environments via symmetry."""
        w, h = self.w, self.h
        passable = self._passable
        pw = self._pw
        for i, env in known_env.items():
            mi = mirror_idx(i, sym, w, h)
            mpi = mi + 2 * (mi // w) + pw + 1
            if passable[mpi] == 2:
                passable[mpi] = 0 if env == Environment.WALL else 1
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

    def emit_vis(self) -> None:
        """Emit a grid showing wall / unseen / reachable / seen-unreachable
        / frontier state for every real tile.
        """
        w, h = self.w, self.h
        pw = self._pw
        passable = self._passable
        reachable = self._reachable

        # State encoding: 0 wall, 1 unseen, 2 reachable, 3 seen-unreachable.
        # Frontier tiles get -1 so they're highlighted via the special map.
        frontier_set = set(self._frontier)
        data: list[int] = [0] * (w * h)
        for ry in range(h):
            for rx in range(w):
                pi = (ry + 1) * pw + (rx + 1)
                ri = ry * w + rx
                if pi in frontier_set:
                    data[ri] = -1
                    continue
                p = passable[pi]
                if p == 0:
                    data[ri] = 0
                elif p == 2:
                    data[ri] = 1
                elif reachable[pi]:
                    data[ri] = 2
                else:
                    data[ri] = 3

        emit(
            reachable=Grid(
                data,
                palette=Palette(
                    stops=[(0.0, 0, 0, 0, 0)],
                    special={
                        0: (40, 40, 40, 200),  # wall — dark grey
                        1: (0, 0, 0, 0),  # unseen — transparent
                        2: (0, 200, 0, 80),  # reachable — green
                        3: (200, 120, 0, 140),  # seen but unreachable — orange
                        -1: (255, 0, 255, 220),  # frontier — magenta
                    },
                ),
            ),
        )

    def is_reachable(self, pos: Position) -> bool:
        """Return True if `pos` is currently known to be reachable."""
        pi = (pos.y + 1) * self._pw + (pos.x + 1)
        return self._reachable[pi]

    def pick_frontier(
        self, cur_pos: Position, core_pos: Position, sym: Symmetry
    ) -> Position | None:
        """Pick a reachable frontier tile (one adjacent to unseen area).

        Tie-break: chebyshev(core, cell) - chebyshev(center, cell). Staying
        near the core is cheap; the negative center term rewards cells whose
        center-distance is large... note: minimizing this actually prefers
        cells close to core and *far* from center. Keeping as specified.
        """
        if not self._frontier:
            return None
        pw = self._pw
        self.w // 2
        self.h // 2
        kx = core_pos.x
        ky = core_pos.y
        px = cur_pos.x
        py = cur_pos.y
        best_pi = -1
        best_key = 1 << 30

        for pi in self._frontier:
            x = pi % pw - 1
            y = pi // pw - 1
            cur_d = max(abs(x - px), abs(y - py))
            core_d = max(abs(x - kx), abs(y - ky))
            key = core_d**0.75 + cur_d
            if key < best_key:
                best_key = key
                best_pi = pi
        if best_pi < 0:
            return None
        return Position(best_pi % pw - 1, best_pi // pw - 1)
