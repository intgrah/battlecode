"""BFS pathfinding for builder bots.

Backwards BFS from the goal. Stores a flat distance array so that
stepping toward the goal is a single neighbor scan.

Internal grid is padded by 1 tile on each side (sentinel border).
All border tiles are permanently impassable, so every real tile has
8 valid neighbors — no bounds checks needed anywhere.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from cambc import Controller, Direction, EntityType, Environment, Position
from lib.visualiser.src.visualiser import Grid, Palette, VectorField, emit
from symmetry import Symmetry, mirror_idx

if TYPE_CHECKING:
    from collections.abc import Callable

INF = 1_000_000

DIR8_DELTA: tuple[tuple[int, int], ...] = tuple(
    d.delta()
    for d in (
        Direction.NORTHEAST,
        Direction.SOUTHEAST,
        Direction.SOUTHWEST,
        Direction.NORTHWEST,
        Direction.NORTH,
        Direction.EAST,
        Direction.SOUTH,
        Direction.WEST,
    )
)

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
    stop_at: int = INF,
) -> None:
    """Run backwards BFS to completion (one level past the agent)."""
    for node in q:
        d = dist[node] + 1
        if d > stop_at:
            return
        if node == cur_idx:
            stop_at = d
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
    """Backwards-BFS navigation for builder bots.

    Maintains a passability grid updated each round from vision.
    Runs BFS backwards from the goal using _pnb (passable-only neighbors)
    so the inner loop has no passability check.

    Internal grid is padded by 1 on each side. Border tiles are always
    impassable, eliminating all bounds checks.
    """

    def __init__(self, w: int, h: int) -> None:
        self.w = w
        self.h = h
        pw = w + 2
        self._pw = pw
        self._rn = w * h  # real tile count
        n = pw * (h + 2)  # padded tile count
        self._n = n
        self._gi = -1

        # Passable grid: border=0, interior=1 (assume all passable initially)
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

        # Neighbor offsets (constant for padded grid)
        self._offsets: tuple[int, ...] = (
            -pw + 1,  # NE
            pw + 1,  # SE
            pw - 1,  # SW
            -pw - 1,  # NW
            -pw,  # N
            1,  # E
            pw,  # S
            -1,  # W
        )

        # Distance array. Unvisited tiles hold INF; cleared on each restart.
        self._dist: list[int] = [INF] * n

        self._q: list[int] = []
        self._cur_dist = INF
        self._cur_idx = -1
        self._gis: list[int] = []

    def update_tile(
        self,
        i: int,
        env: Environment,
        building_type: EntityType | None,
        is_allied_building: bool,
        sym: Symmetry = Symmetry.UNKNOWN,
    ) -> None:
        """Update a single tile's passability and check dirty flags."""
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

        if sym is not Symmetry.UNKNOWN:
            mi = mirror_idx(i, sym, self.w, self.h)
            self._set_passable(mi, passable=env != Environment.WALL)

    def _set_passable(self, i: int, passable: bool) -> None:
        """Write passability to grid and mark dirty if a closer tile changed."""
        # real (x,y) where y=i//w, x=i%w -> padded (y+1)*pw + (x+1)
        # = y*pw + pw + x + 1 = (y*w + x) + 2*y + pw + 1 = i + 2*(i//w) + pw + 1
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
            # Only dirty BFS if tile is closer to goal than agent
            if self._dist[pi] < self._cur_dist:
                self._dirty = True

    def _init_pnb_chunk(self, within_budget: Callable[[], bool]) -> bool:
        """Build pnb tables incrementally, assuming all real tiles passable.

        Single loop over real tiles — all have 8 valid padded neighbors.
        All cardinals skippable (both adjacent diags always exist).
        Returns True when complete.
        """
        w = self.w
        pw = self._pw
        pnb_push = self._pnb_push
        pnb_set = self._pnb_set
        progress = self._pnb_init_progress
        total = self._rn

        # Neighbor offsets
        ne_off, se_off, sw_off, nw_off, n_off, e_off, s_off, w_off = self._offsets

        # Convert progress counter to padded index
        ry, rx = divmod(progress, w)
        pi = (ry + 1) * pw + (rx + 1)

        while progress < total:
            pnb_push[pi] = [pi + ne_off, pi + se_off, pi + sw_off, pi + nw_off]
            pnb_set[pi] = [pi + n_off, pi + e_off, pi + s_off, pi + w_off]
            progress += 1
            rx += 1
            if rx == w:
                rx = 0
                pi += 3  # skip right border + left border of next row
            else:
                pi += 1
            if progress & 255 == 0 and not within_budget():
                self._pnb_init_progress = progress
                return False

        self._pnb_init_progress = total
        return True

    def _rebuild_pnb(self) -> None:
        """Rebuild _pnb for passable tiles affected by passability changes."""
        passable = self._passable
        pnb_push = self._pnb_push
        pnb_set = self._pnb_set
        offsets = self._offsets

        for pi in self._pnb_dirty:
            push = pnb_push[pi]
            assign = pnb_set[pi]
            push.clear()
            assign.clear()
            if not passable[pi]:
                continue

            ne, se, sw, nw, n, e, s, w = tuple(pi + off for off in offsets)

            # Diagonals — always enqueue
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

            # Cardinals — skip enqueue if both adjacent diagonals are passable
            if passable[n]:
                (assign if has_ne and has_nw else push).append(n)
            if passable[e]:
                (assign if has_ne and has_se else push).append(e)
            if passable[s]:
                (assign if has_se and has_sw else push).append(s)
            if passable[w]:
                (assign if has_sw and has_nw else push).append(w)

        self._pnb_dirty.clear()

    def mirror_known(self, sym: Symmetry, known_env: dict[int, Environment]) -> None:
        """Bulk-mirror all previously observed tile environments via symmetry."""
        w, h = self.w, self.h
        for i, env in known_env.items():
            mi = mirror_idx(i, sym, w, h)
            self._set_passable(mi, passable=env != Environment.WALL)
        self._dirty = True

    def get_passable(self, pos: Position) -> bool:
        """Return passability at a position."""
        pi = (pos.y + 1) * self._pw + (pos.x + 1)
        return self._passable[pi]

    def set_goal(self, goal: Position) -> None:
        """Change to a single goal. Marks dirty so the search resets."""
        self.set_goals([goal])

    def set_goals(self, goals: list[Position]) -> None:
        """Change to multiple goals. Marks dirty so the search resets."""
        pw = self._pw
        gis = [(g.y + 1) * pw + (g.x + 1) for g in goals]
        if gis != self._gis:
            self._gis = gis
            self._dirty = True

    def _compute(self) -> None:
        """Reset BFS state for a fresh search from goals."""
        self._dist[:] = [INF] * self._n
        q = self._q
        q.clear()
        for gi in self._gis:
            self._dist[gi] = 0
            q.append(gi)

        _bfs_compute(self._pnb_push, self._pnb_set, self._dist, self._q, self._cur_idx)

    def emit_vis(self) -> None:
        """Emit the BFS distance field and direction arrows to the visualiser."""
        dist = self._dist
        pw = self._pw
        w, h = self.w, self.h
        rn = self._rn
        pnb_push = self._pnb_push
        pnb_set = self._pnb_set
        angles: list[float | None] = [None] * rn
        dist_list: list[int] = [-1] * rn

        for ry in range(h):
            for rx in range(w):
                pi = (ry + 1) * pw + (rx + 1)
                ri = ry * w + rx
                di = dist[pi]
                if di >= INF:
                    continue
                dist_list[ri] = di
                if di <= 0:
                    continue
                best = di
                bx, by = 0, 0
                for ni in pnb_push[pi] + pnb_set[pi]:
                    dn = dist[ni]
                    if dn < best:
                        best = dn
                        bx = ni % pw - pi % pw
                        by = ni // pw - pi // pw
                if best < di:
                    angles[ri] = math.atan2(by, bx)

        emit(
            dist=Grid(
                dist_list,
                palette=Palette(
                    stops=[(0.0, 0, 200, 0, 120), (1.0, 200, 0, 0, 180)],
                    special={-1: (0, 0, 0, 0)},
                ),
            ),
            bfs=VectorField(angles),
        )

    def step(
        self,
        ct: Controller,
        within_budget: Callable[[], bool] = lambda: True,
    ) -> bool:
        """Try to move one step toward the goal. Returns True if movement occurred."""
        # Initial pnb build (all-passable fast path)
        if self._pnb_init_progress < self._rn:
            self._init_pnb_chunk(within_budget)
            return False

        # Rebuild pnb for tiles with passability changes
        if self._pnb_dirty:
            self._rebuild_pnb()

        pw = self._pw
        pos = ct.get_position()
        self._cur_idx = (pos.y + 1) * pw + (pos.x + 1)

        self._dirty = True
        if self._dirty:
            self._compute()
            self._dirty = False

        cur_idx = self._cur_idx
        dist = self._dist
        d = dist[cur_idx]
        self._cur_dist = d

        if d <= 0 or d >= INF:
            return False

        print(f"dist {d}")
        pnb = self._pnb_push[cur_idx] + self._pnb_set[cur_idx]
        for target in (d - 1, d, d + 1):
            # Prefer tiles that are already passable (no road build needed)
            for ni in pnb:
                if dist[ni] != target:
                    continue
                next_pos = Position(ni % pw - 1, ni // pw - 1)
                direction = pos.direction_to(next_pos)
                if ct.can_move(direction):
                    ct.move(direction)
                    return True
            # Fall back to building a road
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

        # Just move in any direction
        for ni in pnb:
            next_pos = Position(ni % pw - 1, ni // pw - 1)
            direction = pos.direction_to(next_pos)
            if ct.can_build_road(next_pos):
                ct.build_road(next_pos)
            if ct.can_move(direction):
                ct.move(direction)
                return True

        return False
