"""BFS pathfinding for builder bots.

Backwards BFS from the goal. Stores a flat distance array so that
stepping toward the goal is a single neighbor scan.

Internal grid is padded by 1 tile on each side (sentinel border).
All border tiles are permanently impassable, so every real tile has
8 valid neighbors — no bounds checks needed anywhere.
"""

from __future__ import annotations

import math
from array import array
from typing import TYPE_CHECKING

from cambc import Position
from grid import PassableGrid
from lib.visualiser.src.visualiser import VectorField, emit_dict

INF = 1_000_000

if TYPE_CHECKING:
    from collections.abc import Callable


class NavBfs:
    """Backwards-BFS navigation for builder bots.

    Uses a PassableGrid for the walkability graph. Runs BFS backwards
    from the goal using pnb (passable-only neighbors) so the inner loop
    has no passability check.
    """

    def __init__(
        self, grid: PassableGrid, target_dist: int = 0, range: int = INF
    ) -> None:
        self.grid = grid
        n = grid.n
        self._goals: list[int] = []
        self._target_dist = target_dist
        self._range = range if range < grid.w or range < grid.h else INF

        self._dirty = True

        self._dist: array[int] = array("i", bytes(4 * n))
        self._gen: bytearray = bytearray(n)
        self._g: int = 1

        self._q: array[int] = array("i", bytes(4 * n))
        self._qi = 0
        self._qlen = 0
        self._resumable = False
        self._cur_dist = -1
        self._cur_idx = -1

    def mark_dirty(self) -> None:
        """Force a BFS restart on the next step."""
        self._dirty = True

    def notify_closer_tile_changed(self, pi: int) -> None:
        """Mark BFS dirty if the tile is closer to goal than the agent."""
        if self._gen[pi] == self._g:
            d = self._dist[pi]
            if d < self._cur_dist:
                self._dirty = True

    def change_goal(self, goals: list[Position]) -> None:
        """Replace goals. Always marks dirty."""
        pw = self.grid.pw
        self._goals = [(g.y + 1) * pw + (g.x + 1) for g in goals]
        self._dirty = True

    def _restart(self) -> None:
        """Reset BFS state for a fresh search from goals."""
        g = self._g + 1
        if g > 255:
            g = 1
            self._gen[:] = b"\x00" * len(self._gen)
        self._g = g
        q = self._q
        qlen = 0
        for gi in self._goals:
            self._dist[gi] = 0
            self._gen[gi] = g
            q[qlen] = gi
            qlen += 1
        self._qi = 0
        self._qlen = qlen
        self._resumable = True

    def emit_vis(self) -> None:
        """Emit the BFS distance field and direction arrows to the visualiser."""
        grid = self.grid
        dist = self._dist
        gen = self._gen
        g = self._g
        pw = grid.pw
        w, h = grid.w, grid.h
        rn = grid.rn
        pnb_push = grid.pnb_push
        pnb_set = grid.pnb_set
        angles: list[float | None] = [None] * rn

        for ry in range(h):
            for rx in range(w):
                pi = (ry + 1) * pw + (rx + 1)
                ri = ry * w + rx
                if gen[pi] != g:
                    continue
                di = dist[pi]
                if di <= 0:
                    continue
                best = di
                bx, by = 0, 0
                for ni in pnb_push[pi] + pnb_set[pi]:
                    if gen[ni] != g:
                        continue
                    dn = dist[ni]
                    if dn < best:
                        best = dn
                        bx = ni % pw - pi % pw
                        by = ni // pw - pi // pw
                if best < di:
                    angles[ri] = math.atan2(by, bx)

        emit_dict({"bfs": VectorField(angles)})

    def _compute(self, within_budget: Callable[[], bool]) -> bool:
        """Run/resume backwards BFS. Returns True if agent tile is reached."""
        grid = self.grid
        pnb_push = grid.pnb_push
        pnb_set = grid.pnb_set
        dist = self._dist
        gen = self._gen
        g = self._g
        q = self._q
        qi = self._qi
        qlen = self._qlen
        cur_idx = self._cur_idx
        # Stop once we've processed one level past the agent
        cd = dist[cur_idx] if cur_idx >= 0 and gen[cur_idx] == g else -1
        stop_at = cd + 1 if cd != -1 else 1_000_000
        while qi < qlen:
            node = q[qi]
            qi += 1
            d = dist[node] + 1
            if node == cur_idx:
                stop_at = d
            if d > stop_at:
                self._qi = qi - 1
                self._qlen = qlen
                return True
            for ni in pnb_push[node]:
                if gen[ni] == g:
                    continue
                gen[ni] = g
                dist[ni] = d
                q[qlen] = ni
                qlen += 1
            for ni in pnb_set[node]:
                if gen[ni] == g:
                    continue
                if ni == cur_idx:
                    stop_at = d + 1
                gen[ni] = g
                dist[ni] = d
            if qi & 255 == 0 and not within_budget():
                print("budget exceeded")
                self._qi = qi
                self._qlen = qlen
                return False
        print("exhausted route")
        self._qi = qi
        self._qlen = qlen
        return True

    def _compute_range(self, within_budget: Callable[[], bool]) -> bool:
        """Run/resume backwards BFS with range limit. Returns True if agent tile is reached."""
        grid = self.grid
        pnb_push = grid.pnb_push
        pnb_set = grid.pnb_set
        dist = self._dist
        gen = self._gen
        g = self._g
        q = self._q
        qi = self._qi
        qlen = self._qlen
        cur_idx = self._cur_idx
        pw = self.grid.pw
        range = self._range

        cur_y = cur_idx // pw
        cur_x = cur_idx - cur_y * pw
        range_yn = cur_y - range
        range_yp = cur_y + range
        range_xn = cur_x - range
        range_xp = cur_x + range

        # Stop once we've processed one level past the agent
        cd = dist[cur_idx] if cur_idx >= 0 and gen[cur_idx] == g else -1
        stop_at = cd + 1 if cd != -1 else 1_000_000
        while qi < qlen:
            node = q[qi]
            qi += 1

            n_y = node // pw
            n_x = node - n_y * pw
            if n_x < range_xn or n_x > range_xp or n_y < range_yn or n_y > range_yp:
                continue

            d = dist[node] + 1
            if node == cur_idx:
                stop_at = d
            if d > stop_at:
                self._qi = qi - 1
                self._qlen = qlen
                return True
            for ni in pnb_push[node]:
                if gen[ni] == g:
                    continue
                gen[ni] = g
                dist[ni] = d
                q[qlen] = ni
                qlen += 1
            for ni in pnb_set[node]:
                if gen[ni] == g:
                    continue
                if ni == cur_idx:
                    stop_at = d + 1
                gen[ni] = g
                dist[ni] = d
            if qi & 255 == 0 and not within_budget():
                print("budget exceeded")
                self._qi = qi
                self._qlen = qlen
                return False
        print("exhausted route")
        self._qi = qi
        self._qlen = qlen
        return True

    def step(
        self,
        pos: Position,
        within_budget: Callable[[], bool] = lambda: True,
    ) -> tuple[int, int, int, int, int, int, int, int]:
        """Compute BFS and return weights for each of the 8 directions.

        Returns (NE, SE, SW, NW, N, E, S, W) where each weight is
        dist[adjacent] - dist[current], or INF if the adjacent tile has
        no distance. Returns all zeros if BFS has no data for the current tile.

        Direction order matches grid.offsets: NE, SE, SW, NW, N, E, S, W.
        """
        grid = self.grid
        _zero = (0, 0, 0, 0, 0, 0, 0, 0)

        # Initial pnb build (all-passable fast path)
        if not grid.ready:
            grid.init_pnb_chunk(within_budget)
            return _zero

        # Rebuild pnb for tiles with passability changes
        if grid.has_dirty_pnb:
            grid.rebuild_pnb()

        pw = grid.pw
        cur_idx = (pos.y + 1) * pw + (pos.x + 1)
        self._cur_idx = cur_idx

        if self._dirty:
            self._restart()
            self._dirty = False
        elif (
            not self._resumable
            and self._gen[cur_idx] != self._g
            and self._qi < self._qlen
        ):
            # Agent moved beyond the computed frontier — resume
            self._resumable = True
        if self._resumable:
            finished = (
                self._compute(within_budget)
                if self._range >= INF
                else self._compute_range(within_budget)
            )
            if finished:
                print(f"steps {self._qi}")
                self._resumable = self._qi < self._qlen

        dist = self._dist
        gen = self._gen
        g = self._g
        d = dist[cur_idx] if gen[cur_idx] == g else -1
        self._cur_dist = d

        if d < 0:
            return _zero

        td = self._target_dist
        offset = abs(d - td)
        print(f"dist {offset}")

        return tuple(
            abs(dist[cur_idx + off] - td) - offset if gen[cur_idx + off] == g else INF
            for off in grid.offsets
        )
