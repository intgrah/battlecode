"""BFS pathfinding for builder bots.

Backwards BFS from the goal. Stores a flat distance array so that
stepping toward the goal is a single neighbor scan.

Uses double-buffered dist arrays: the stable buffer is always usable for
movement, while the wip buffer is computed incrementally. On completion
the buffers swap.
"""

from __future__ import annotations

import math
from array import array
from typing import TYPE_CHECKING

from cambc import Controller, Direction, EntityType, Environment, Position
from symmetry import Symmetry, mirror_idx
#from lib.visualiser.src.visualiser import Grid, Palette, VectorField, emit

if TYPE_CHECKING:
    from collections.abc import Callable

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

# DIR8_DELTA order: NE(0), SE(1), SW(2), NW(3), N(4), E(5), S(6), W(7)
# For each cardinal (indices 4-7), the two adjacent diagonal indices.
_CARDINAL_ADJ_DIAGS: tuple[tuple[int, int], ...] = (
    (0, 3),  # N: NE, NW
    (0, 1),  # E: NE, SE
    (1, 2),  # S: SE, SW
    (2, 3),  # W: SW, NW
)


def _get_dir_nb(i: int, w: int, h: int) -> tuple[int, ...]:
    """Return 8 directional neighbor indices for tile i, -1 for out-of-bounds."""
    cx, cy = i % w, i // w
    return tuple(
        ny * w + nx
        if 0 <= (nx := cx + dx) < w and 0 <= (ny := cy + dy) < h
        else -1
        for dx, dy in DIR8_DELTA
    )


def _compute_pnb(
    dir_nb_i: tuple[int, ...],
    passable: list[int],
) -> tuple[list[int], list[int], list[int]]:
    """Compute pnb split for a single passable tile.

    Returns (pnb_full, pnb_push, pnb_set) where:
    - pnb_full: all passable neighbors (for movement)
    - pnb_push: neighbors to enqueue in BFS
    - pnb_set: neighbors to assign distance only (skippable cardinals)

    DIR8_DELTA order: NE(0), SE(1), SW(2), NW(3), N(4), E(5), S(6), W(7)
    Cardinal adj diags: N->NE,NW  E->NE,SE  S->SE,SW  W->SW,NW
    """
    ne, se, sw, nw, n, e, s, w = dir_nb_i

    full: list[int] = []
    push: list[int] = []
    assign: list[int] = []

    # Diagonals — always enqueue
    has_ne = ne != -1 and passable[ne]
    if has_ne:
        full.append(ne)
        push.append(ne)
    has_se = se != -1 and passable[se]
    if has_se:
        full.append(se)
        push.append(se)
    has_sw = sw != -1 and passable[sw]
    if has_sw:
        full.append(sw)
        push.append(sw)
    has_nw = nw != -1 and passable[nw]
    if has_nw:
        full.append(nw)
        push.append(nw)

    # Cardinals — skip enqueue if both adjacent diagonals are passable
    if n != -1 and passable[n]:
        full.append(n)
        (assign if has_ne and has_nw else push).append(n)
    if e != -1 and passable[e]:
        full.append(e)
        (assign if has_ne and has_se else push).append(e)
    if s != -1 and passable[s]:
        full.append(s)
        (assign if has_se and has_sw else push).append(s)
    if w != -1 and passable[w]:
        full.append(w)
        (assign if has_sw and has_nw else push).append(w)

    return full, push, assign


class NavBfs:
    """Backwards-BFS navigation for builder bots.

    Maintains a passability grid updated each round from vision.
    Runs BFS backwards from the goal using _pnb (passable-only neighbors)
    so the inner loop has no passability check.

    Double-buffered: _stable is used for movement, _wip is computed
    incrementally. On completion they swap.
    """

    def __init__(self, w: int, h: int) -> None:
        self.w = w
        self.h = h
        self._n = w * h
        self._gi = -1
        self._passable: list[int] = [1] * (w * h)
        self._pnb: list[list[int]] = [[]] * (w * h)
        self._pnb_push: list[list[int]] = [[]] * (w * h)
        self._pnb_set: list[list[int]] = [[]] * (w * h)
        self._pnb_dirty: set[int] = set()
        self._pnb_init_progress: int = 0
        self._dirty = True

        # Double-buffered dist arrays with generation counters
        n = w * h
        self._stable: array[int] = array("i", bytes(4 * n))
        self._stable_gen: bytearray = bytearray(n)
        self._stable_g: int = 1
        self._wip: array[int] = array("i", bytes(4 * n))
        self._wip_gen: bytearray = bytearray(n)
        self._wip_g: int = 1

        self._q: array[int] = array("i", bytes(4 * n))
        self._qi = 0
        self._qlen = 0
        self._resumable = False
        self._new_goal = True
        self._cur_dist = -1
        self._cur_idx = -1

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

    def _set_passable(self, i: int, *, passable: bool) -> None:
        """Write passability to grid and mark dirty if a closer tile changed."""
        old = self._passable[i]
        if old != passable:
            self._passable[i] = passable
            # Mark passable tiles needing pnb rebuild (self + neighbors)
            pnb_dirty = self._pnb_dirty
            if passable:
                pnb_dirty.add(i)
            else:
                pnb_dirty.discard(i)
            for ni in _get_dir_nb(i, self.w, self.h):
                if ni == -1:
                    continue
                if self._passable[ni]:
                    pnb_dirty.add(ni)
                else:
                    pnb_dirty.discard(ni)
            # Only dirty BFS if tile is closer to goal than agent
            if self._stable_gen[i] == self._stable_g:
                d = self._stable[i]
                if d < self._cur_dist:
                    self._dirty = True

    def _init_pnb_chunk(self, within_budget: Callable[[], bool]) -> bool:
        """Build pnb tables incrementally, assuming all tiles passable.

        Phase 1: interior tiles (no bounds checks, all 8 neighbors valid).
        Phase 2: border fixup.
        Returns True when complete.
        """
        n = self._n
        w, h = self.w, self.h
        pnb = self._pnb
        pnb_push = self._pnb_push
        pnb_set = self._pnb_set
        i = self._pnb_init_progress

        # Phase 1: interior tiles — all 8 neighbors guaranteed in-bounds
        # All cardinals skippable (both adjacent diags exist)
        while i < n:
            cy, cx = divmod(i, w)
            if cx == 0 or cx == w - 1 or cy == 0 or cy == h - 1:
                # Border tile — handle in phase 2
                i += 1
                continue
            ne = (cy - 1) * w + cx + 1
            se = (cy + 1) * w + cx + 1
            sw = (cy + 1) * w + cx - 1
            nw = (cy - 1) * w + cx - 1
            no = (cy - 1) * w + cx
            ea = cy * w + cx + 1
            so = (cy + 1) * w + cx
            we = cy * w + cx - 1
            pnb[i] = [ne, se, sw, nw, no, ea, so, we]
            pnb_push[i] = [ne, se, sw, nw]
            pnb_set[i] = [no, ea, so, we]
            i += 1
            if i & 127 == 0 and not within_budget():
                self._pnb_init_progress = i
                return False

        # Phase 2: fix up border tiles (Optimized & Inlined)

        # 1. Handle Top and Bottom rows
        for cx in range(w):
            for cy in (0, h - 1):
                if cy == 0 and h == 1 and cx > 0: # Avoid double-processing 1xN grids
                    continue
                    
                idx = cy * w + cx
                dn = _get_dir_nb(idx, w, h)
                pnb[idx] = [ni for ni in dn if ni != -1]
                
                ne, se, sw, nw, no, ea, so, we = dn
                push = []
                assign = []
                
                if ne != -1: push.append(ne)
                if se != -1: push.append(se)
                if sw != -1: push.append(sw)
                if nw != -1: push.append(nw)
                
                if no != -1: (assign if ne != -1 and nw != -1 else push).append(no)
                if ea != -1: (assign if ne != -1 and se != -1 else push).append(ea)
                if so != -1: (assign if se != -1 and sw != -1 else push).append(so)
                if we != -1: (assign if sw != -1 and nw != -1 else push).append(we)
                
                pnb_push[idx] = push
                pnb_set[idx] = assign

        # 2. Handle Left and Right columns (excluding the corners already handled above)
        for cy in range(1, h - 1):
            for cx in (0, w - 1):
                if cx == 0 and w == 1: # Avoid double-processing Mx1 grids
                    continue
                    
                idx = cy * w + cx
                dn = _get_dir_nb(idx, w, h)
                pnb[idx] = [ni for ni in dn if ni != -1]
                
                ne, se, sw, nw, no, ea, so, we = dn
                push = []
                assign = []
                
                if ne != -1: push.append(ne)
                if se != -1: push.append(se)
                if sw != -1: push.append(sw)
                if nw != -1: push.append(nw)
                
                if no != -1: (assign if ne != -1 and nw != -1 else push).append(no)
                if ea != -1: (assign if ne != -1 and se != -1 else push).append(ea)
                if so != -1: (assign if se != -1 and sw != -1 else push).append(so)
                if we != -1: (assign if sw != -1 and nw != -1 else push).append(we)
                
                pnb_push[idx] = push
                pnb_set[idx] = assign

        self._pnb_init_progress = n
        return True

    def _rebuild_pnb(self) -> None:
        """Rebuild _pnb for passable tiles affected by passability changes."""
        passable = self._passable
        w, h = self.w, self.h
        pnb = self._pnb
        pnb_push = self._pnb_push
        pnb_set = self._pnb_set
        for i in self._pnb_dirty:
            dn = _get_dir_nb(i, w, h)
            if passable[i]:
                pnb[i], pnb_push[i], pnb_set[i] = _compute_pnb(dn, passable)
            else:
                pnb[i] = []
                pnb_push[i] = []
                pnb_set[i] = []
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
        return self._passable[pos.y * self.w + pos.x]

    def set_goal(self, goal: Position) -> None:
        """Change the goal. Marks dirty so the search resets."""
        gi = goal.y * self.w + goal.x
        if gi != self._gi:
            self._gi = gi
            self._dirty = True
            self._new_goal = True

    def _restart(self) -> None:
        """Reset wip BFS state for a fresh search from goal."""
        g = self._wip_g + 1
        if g > 255:
            g = 1
            self._wip_gen[:] = b"\x00" * len(self._wip_gen)
        self._wip_g = g
        gi = self._gi
        self._wip[gi] = 0
        self._wip_gen[gi] = self._wip_g
        self._q[0] = gi
        self._qi = 0
        self._qlen = 1
        self._resumable = True

    def _swap(self) -> None:
        """Promote wip to stable."""
        self._stable, self._wip = self._wip, self._stable
        self._stable_gen, self._wip_gen = self._wip_gen, self._stable_gen
        self._stable_g, self._wip_g = self._wip_g, self._stable_g

    def emit_vis(self) -> None:
        """Emit the BFS distance field and direction arrows to the visualiser."""
        dist = self._stable
        gen = self._stable_gen
        g = self._stable_g
        w = self.w
        n = self._n
        pnb = self._pnb
        angles: list[float | None] = [None] * n
        # Build plain list for Grid, using -1 for unvisited cells
        dist_list: list[int] = [-1] * n
        for i in range(n):
            if gen[i] != g:
                continue
            di = dist[i]
            dist_list[i] = di
            if di <= 0:
                continue
            best = di
            bx, by = 0, 0
            for ni in pnb[i]:
                if gen[ni] != g:
                    continue
                dn = dist[ni]
                if dn < best:
                    best = dn
                    bx = ni % w - i % w
                    by = ni // w - i // w
            if best < di:
                angles[i] = math.atan2(by, bx)

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

    def _compute(self, within_budget: Callable[[], bool]) -> bool:
        """Run/resume backwards BFS into wip buffer. Returns True if complete."""
        pnb_push = self._pnb_push
        pnb_set = self._pnb_set
        dist = self._wip
        gen = self._wip_gen
        g = self._wip_g
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

    def step(
        self,
        ct: Controller,
        within_budget: Callable[[], bool] = lambda: True,
    ) -> bool:
        """Try to move one step toward the goal. Returns True if movement occurred."""
        # Initial pnb build (all-passable fast path)
        if self._pnb_init_progress < self._n:
            self._init_pnb_chunk(within_budget)
            return False

        # Rebuild pnb for tiles with passability changes
        if self._pnb_dirty:
            self._rebuild_pnb()

        w = self.w
        pos = ct.get_position()
        self._cur_idx = pos.y * w + pos.x

        if self._dirty:
            self._restart()
            self._dirty = False
        if self._resumable and self._compute(within_budget):
            self._resumable = False
            self._new_goal = False
            self._swap()

        # Use stable buffer, fall back to wip if stable is stale (new goal)
        cur_idx = self._cur_idx
        dist = self._stable
        gen = self._stable_gen
        g = self._stable_g
        d = dist[cur_idx] if gen[cur_idx] == g else -1
        if self._new_goal:
            dist = self._wip
            gen = self._wip_gen
            g = self._wip_g
            d = dist[cur_idx] if gen[cur_idx] == g else -1
        self._cur_dist = d

        if d <= 0:
            return False

        print(f"dist {d}")
        pnb = self._pnb[cur_idx]
        options = (d - 1,) if self._resumable else (d - 1, d, d + 1)
        for target in options:
            # Prefer tiles that are already passable (no road build needed)
            for ni in pnb:
                if gen[ni] != g or dist[ni] != target:
                    continue
                next_pos = Position(ni % w, ni // w)
                direction = pos.direction_to(next_pos)
                if ct.can_move(direction):
                    ct.move(direction)
                    return True
            # Fall back to building a road
            for ni in pnb:
                if gen[ni] != g or dist[ni] != target:
                    continue
                next_pos = Position(ni % w, ni // w)
                direction = pos.direction_to(next_pos)
                if ct.can_build_road(next_pos):
                    ct.build_road(next_pos)
                if ct.can_move(direction):
                    ct.move(direction)
                    return True

        # Just move in any direction, and continue bfs (we didn't compute bfs behind us)
        for ni in pnb:
            next_pos = Position(ni % w, ni // w)
            direction = pos.direction_to(next_pos)
            if ct.can_build_road(next_pos):
                ct.build_road(next_pos)
            if ct.can_move(direction):
                print("backtracked, continuing compute")
                if not self._resumable:
                    self._resumable = True
                    self._swap()
                ct.move(direction)
                return True

        return False
