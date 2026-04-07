"""BFS navigation — combined grid + pathfinding.

Ported from adgato/bfs_test/bfs.py with:
- Inline offset optimization in _rebuild_pnb (2x faster)
- Removed visualiser imports
- Removed debug prints
- Added set_passable_pi for direct padded-index access
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Controller, EntityType, Environment, Position
from symmetry import mirror_idx

if TYPE_CHECKING:
    from collections.abc import Callable

    from util import Symmetry

INF = 1_000_000

_WALKABLE_BUILDINGS: frozenset[EntityType] = frozenset(
    {
        EntityType.ROAD,
        EntityType.CONVEYOR,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.SPLITTER,
        EntityType.BRIDGE,
    },
)


def _bfs_compute(
    pnb_push: list[list[int]],
    pnb_set: list[list[int]],
    dist: list[int],
    q: list[int],
    cur_idx: int,
) -> None:
    """Run backwards BFS to completion (one level past the agent)."""
    stop_at = INF
    for node in q:
        d = dist[node] + 1
        if node == cur_idx:
            stop_at = d
        if d > stop_at:
            return
        for ni in pnb_push[node]:
            if d < dist[ni]:
                dist[ni] = d
                q.append(ni)
        for ni in pnb_set[node]:
            if d < dist[ni]:
                if ni == cur_idx:
                    stop_at = d + 1
                dist[ni] = d


class NavBfs:
    """Backwards-BFS navigation with built-in passability grid.

    Padded by 1 tile on each side — border tiles permanently impassable,
    no bounds checks needed. Call update_tile() from vision scan,
    set_goal()/set_goals() to change target, step() to move.
    """

    def __init__(self, w: int, h: int) -> None:
        self.w = w
        self.h = h
        pw = w + 2
        self._pw = pw
        self._rn = w * h
        n = pw * (h + 2)
        self._n = n
        self._gi = -1

        # Passable grid: border=0, interior=1
        self._passable: list[int] = [1] * n
        row_data = [0] * pw
        self._passable[0:pw] = row_data
        self._passable[(h + 1) * pw : (h + 1) * pw + pw] = row_data
        for ry in range(1, h + 1):
            self._passable[ry * pw] = 0
            self._passable[ry * pw + pw - 1] = 0

        self._pnb_push: list[list[int]] = [[]] * n
        self._pnb_set: list[list[int]] = [[]] * n
        self._pnb_dirty: set[int] = set()
        self._pnb_init_progress: int = 0
        self._dirty = True

        self._offsets: tuple[int, ...] = (
            -pw + 1,
            pw + 1,
            pw - 1,
            -pw - 1,
            -pw,
            1,
            pw,
            -1,
        )

        self._dist: list[int] = [INF] * n
        self._q: list[int] = []
        self._cur_dist = INF
        self._cur_idx = -1
        self._gis: list[int] = []

    def real_to_padded(self, i: int) -> int:
        return i + 2 * (i // self.w) + self._pw + 1

    def update_tile(
        self,
        i: int,
        env: Environment,
        building_type: EntityType | None,
        is_allied_building: bool,
        sym: Symmetry | None = None,
    ) -> None:
        """Update a single tile's passability from vision data."""
        if env == Environment.WALL:
            passable = False
        elif building_type is None:
            passable = True
        elif building_type == EntityType.CORE:
            passable = is_allied_building
        elif building_type == EntityType.MARKER or building_type in _WALKABLE_BUILDINGS:
            passable = True
        else:
            passable = False

        self._set_passable(i, passable=passable)

        if sym is not None:
            mi = mirror_idx(i, sym, self.w, self.h)
            self._set_passable(mi, passable=env != Environment.WALL)

    def _set_passable(self, i: int, passable: bool) -> None:
        pi = i + 2 * (i // self.w) + self._pw + 1
        old = self._passable[pi]
        if old != passable:
            self._passable[pi] = passable
            pnb_dirty = self._pnb_dirty
            if passable:
                pnb_dirty.add(pi)
            else:
                pnb_dirty.discard(pi)
            for off in self._offsets:
                ni = pi + off
                if self._passable[ni]:
                    pnb_dirty.add(ni)
                else:
                    pnb_dirty.discard(ni)
            if self._dist[pi] < self._cur_dist:
                self._dirty = True

    def set_passable_at(self, i: int, passable: bool) -> None:
        """Public passability override (e.g. for launcher danger zones)."""
        self._set_passable(i, passable)

    def is_passable(self, pos: Position) -> bool:
        """Check if a tile is passable for walking."""
        pi = (pos.y + 1) * self._pw + (pos.x + 1)
        return bool(self._passable[pi])

    def mirror_known(self, sym: Symmetry, known_env: dict[int, Environment]) -> None:
        """Bulk-mirror walls via symmetry."""
        w, h = self.w, self.h
        for i, env in known_env.items():
            mi = mirror_idx(i, sym, w, h)
            self._set_passable(mi, passable=env != Environment.WALL)
        self._dirty = True

    def _init_pnb_chunk(self, within_budget: Callable[[], bool]) -> bool:
        w = self.w
        pw = self._pw
        pnb_push = self._pnb_push
        pnb_set = self._pnb_set
        progress = self._pnb_init_progress
        total = self._rn
        ne_off, se_off, sw_off, nw_off, n_off, e_off, s_off, w_off = self._offsets
        ry, rx = divmod(progress, w)
        pi = (ry + 1) * pw + (rx + 1)
        while progress < total:
            pnb_push[pi] = [pi + ne_off, pi + se_off, pi + sw_off, pi + nw_off]
            pnb_set[pi] = [pi + n_off, pi + e_off, pi + s_off, pi + w_off]
            progress += 1
            rx += 1
            if rx == w:
                rx = 0
                pi += 3
            else:
                pi += 1
            if progress & 255 == 0 and not within_budget():
                self._pnb_init_progress = progress
                return False
        self._pnb_init_progress = total
        return True

    def _rebuild_pnb(self) -> None:
        """Rebuild pnb for dirty tiles. Inline offsets (2x faster than tuple())."""
        passable = self._passable
        pnb_push = self._pnb_push
        pnb_set = self._pnb_set
        ne_off, se_off, sw_off, nw_off, n_off, e_off, s_off, w_off = self._offsets
        for pi in self._pnb_dirty:
            push = pnb_push[pi]
            assign = pnb_set[pi]
            push.clear()
            assign.clear()
            if not passable[pi]:
                continue
            ne = pi + ne_off
            se = pi + se_off
            sw = pi + sw_off
            nw = pi + nw_off
            n = pi + n_off
            e = pi + e_off
            s = pi + s_off
            w = pi + w_off
            has_ne = passable[ne]
            has_se = passable[se]
            has_sw = passable[sw]
            has_nw = passable[nw]
            if has_ne:
                push.append(ne)
            if has_se:
                push.append(se)
            if has_sw:
                push.append(sw)
            if has_nw:
                push.append(nw)
            if passable[n]:
                (assign if has_ne and has_nw else push).append(n)
            if passable[e]:
                (assign if has_ne and has_se else push).append(e)
            if passable[s]:
                (assign if has_se and has_sw else push).append(s)
            if passable[w]:
                (assign if has_sw and has_nw else push).append(w)
        self._pnb_dirty.clear()

    def set_goal(self, goal: Position) -> None:
        self.set_goals([goal])

    def set_goals(self, goals: list[Position]) -> None:
        pw = self._pw
        gis = [(g.y + 1) * pw + (g.x + 1) for g in goals]
        if gis != self._gis:
            self._gis = gis
            self._dirty = True

    def _compute(self) -> None:
        self._dist[:] = [INF] * self._n
        q = self._q
        q.clear()
        for gi in self._gis:
            self._dist[gi] = 0
            q.append(gi)
        _bfs_compute(self._pnb_push, self._pnb_set, self._dist, self._q, self._cur_idx)

    def get_dist(self, pos: Position) -> int:
        """Get BFS distance at a position (after step/compute)."""
        pi = (pos.y + 1) * self._pw + (pos.x + 1)
        return self._dist[pi]

    def step(
        self,
        ct: Controller,
        within_budget: Callable[[], bool] = lambda: True,
    ) -> bool:
        """Move one step toward goal. Builds road if needed. Returns True if moved."""
        if self._pnb_init_progress < self._rn:
            self._init_pnb_chunk(within_budget)
            return False

        if self._pnb_dirty:
            self._rebuild_pnb()

        pw = self._pw
        pos = ct.get_position()
        self._cur_idx = (pos.y + 1) * pw + (pos.x + 1)

        if self._dirty:
            self._compute()
            self._dirty = False

        cur_idx = self._cur_idx
        dist = self._dist
        d = dist[cur_idx]
        self._cur_dist = d

        if d <= 0 or d >= INF:
            return False

        pnb = self._pnb_push[cur_idx] + self._pnb_set[cur_idx]
        for target in (d - 1, d, d + 1):
            for ni in pnb:
                if dist[ni] != target:
                    continue
                next_pos = Position(ni % pw - 1, ni // pw - 1)
                direction = pos.direction_to(next_pos)
                if ct.can_move(direction):
                    ct.move(direction)
                    return True
            for ni in pnb:
                if dist[ni] != target:
                    continue
                next_pos = Position(ni % pw - 1, ni // pw - 1)
                direction = pos.direction_to(next_pos)
                if ct.can_build_road(next_pos):
                    ct.build_road(next_pos)
                if ct.can_move(direction):
                    ct.move(direction)
                    return True

        # Backtrack: move in any passable direction
        for ni in pnb:
            next_pos = Position(ni % pw - 1, ni // pw - 1)
            direction = pos.direction_to(next_pos)
            if ct.can_build_road(next_pos):
                ct.build_road(next_pos)
            if ct.can_move(direction):
                ct.move(direction)
                return True

        return False

    def step_no_build(self, ct: Controller) -> bool:
        """Move one step toward goal WITHOUT building. For chain-building turns."""
        if self._pnb_init_progress < self._rn or not self._gis:
            return False

        if self._pnb_dirty:
            self._rebuild_pnb()

        pw = self._pw
        pos = ct.get_position()
        self._cur_idx = (pos.y + 1) * pw + (pos.x + 1)

        if self._dirty:
            self._compute()
            self._dirty = False

        cur_idx = self._cur_idx
        dist = self._dist
        d = dist[cur_idx]

        if d <= 0 or d >= INF:
            return False

        pnb = self._pnb_push[cur_idx] + self._pnb_set[cur_idx]
        for target in (d - 1, d, d + 1):
            for ni in pnb:
                if dist[ni] != target:
                    continue
                next_pos = Position(ni % pw - 1, ni // pw - 1)
                direction = pos.direction_to(next_pos)
                if ct.can_move(direction):
                    ct.move(direction)
                    return True
        return False
