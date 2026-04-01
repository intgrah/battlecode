"""BFS pathfinding for builder bots.

Backwards BFS from the goal. Stores a flat distance array so that
stepping toward the goal is a single neighbor scan.

Uses double-buffered dist arrays: the stable buffer is always usable for
movement, while the wip buffer is computed incrementally. On completion
the buffers swap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Controller, Direction, EntityType, Environment, Position
from symmetry import Symmetry, mirror_idx

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


def _build_nb_chunk(
    nb: list[list[int]],
    pnb: list[list[int]],
    w: int,
    h: int,
    passable: list[int],
    start: int,
    within_budget: Callable[[], bool],
) -> int:
    """Compute neighbor tables incrementally. Returns next index to resume from."""
    n = w * h
    for i in range(start, n):
        cx, cy = i % w, i // w
        for dx, dy in DIR8_DELTA:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                ni = ny * w + nx
                nb[i].append(ni)
                if passable[i] and passable[ni]:
                    pnb[i].append(ni)
        if i & 15 == 0 and not within_budget():
            return i + 1
    return n


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
        self._nb: list[list[int]] = [[] for _ in range(w * h)]
        self._pnb: list[list[int]] = [[] for _ in range(w * h)]
        self._nb_progress = 0
        self._pnb_dirty: set[int] = set()
        self._dirty = True

        # Double-buffered dist arrays (each with own touched list)
        self._stable: list[int] = [-1] * (w * h)
        self._stable_touched: list[int] = []
        self._wip: list[int] = [-1] * (w * h)
        self._wip_touched: list[int] = []

        self._q: list[int] = [0] * (w * h)
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
        is_builder: bool,
        sym: Symmetry = Symmetry.UNKNOWN,
    ) -> None:
        """Update a single tile's passability and check dirty flags."""
        if env == Environment.WALL:
            passable = False
        elif building_type is None:
            passable = True
        elif building_type == EntityType.CORE:
            passable = is_allied_building
        elif building_type == EntityType.MARKER:
            passable = True
        elif building_type in _WALKABLE_BUILDINGS:
            passable = True
        else:
            passable = False

        self._set_passable(i, passable)

        if sym is not Symmetry.UNKNOWN:
            mi = mirror_idx(i, sym, self.w, self.h)
            self._set_passable(mi, env != Environment.WALL)

    def _set_passable(self, i: int, passable: bool) -> None:
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
            for ni in self._nb[i]:
                if self._passable[ni]:
                    pnb_dirty.add(ni)
                else:
                    pnb_dirty.discard(ni)
            # Only dirty BFS if tile is closer to goal than agent
            d = self._stable[i]
            if d != -1 and d < self._cur_dist:
                self._dirty = True

    def _rebuild_pnb(self) -> None:
        """Rebuild _pnb for passable tiles affected by passability changes."""
        passable = self._passable
        nb = self._nb
        pnb = self._pnb
        for i in self._pnb_dirty:
            assert passable[i]
            pnb[i] = [ni for ni in nb[i] if passable[ni]]
        self._pnb_dirty.clear()

    def mirror_known(self, sym: Symmetry, known_env: dict[int, Environment]) -> None:
        """Bulk-mirror all previously observed tile environments via symmetry."""
        w, h = self.w, self.h
        for i, env in known_env.items():
            mi = mirror_idx(i, sym, w, h)
            self._set_passable(mi, env != Environment.WALL)
        self._dirty = True

    def begin_update(self) -> None:
        """Prepare dirty-checking state before iterating tiles."""

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
        wip = self._wip
        for i in self._wip_touched:
            wip[i] = -1
        self._wip_touched.clear()
        gi = self._gi
        wip[gi] = 0
        self._wip_touched.append(gi)
        self._q[0] = gi
        self._qi = 0
        self._qlen = 1
        self._resumable = True

    def _swap(self) -> None:
        """Promote wip to stable."""
        self._stable, self._wip = self._wip, self._stable
        self._stable_touched, self._wip_touched = self._wip_touched, self._stable_touched

    def _compute(self, within_budget: Callable[[], bool]) -> bool:
        """Run/resume backwards BFS into wip buffer. Returns True if complete."""
        pnb = self._pnb
        dist = self._wip
        touched = self._wip_touched
        q = self._q
        qi = self._qi
        qlen = self._qlen
        cur_idx = self._cur_idx
        # Stop once we've processed one level past the agent
        cd = dist[cur_idx] if cur_idx >= 0 else -1
        stop_depth = cd + 1 if cd != -1 else 1_000_000
        while qi < qlen:
            node = q[qi]
            qi += 1
            d = dist[node] + 1
            if d > stop_depth + 1:
                self._qi = qi - 1
                self._qlen = qlen
                print(f"stopped at depth {stop_depth}")
                return True
            for ni in pnb[node]:
                if dist[ni] != -1:
                    continue
                dist[ni] = d
                touched.append(ni)
                q[qlen] = ni
                qlen += 1
                # Update stop depth once we reach the agent
                if ni == cur_idx:
                    stop_depth = d + 1
            if qi & 63 == 0 and not within_budget():
                self._qi = qi
                self._qlen = qlen
                return False
        self._qi = qi
        self._qlen = qlen
        return True

    def step(
        self,
        ct: Controller,
        within_budget: Callable[[], bool] = lambda: True,
    ) -> bool:
        """Try to move one step toward the goal. Returns True if movement occurred."""
        # Continue building neighbor table if not done
        if self._nb_progress < self._n:
            self._nb_progress = _build_nb_chunk(
                self._nb, self._pnb, self.w, self.h, self._passable,
                self._nb_progress, within_budget,
            )
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
        if self._resumable:
            if self._compute(within_budget):
                self._resumable = False
                self._new_goal = False
                self._swap()

        # Use stable buffer, fall back to wip if stable is stale (new goal)
        cur_idx = self._cur_idx
        dist = self._stable
        d = dist[cur_idx]
        if self._new_goal:
            dist = self._wip
            d = dist[cur_idx]
        self._cur_dist = d
        if d <= 0:
            return False
        
        pnb = self._pnb[cur_idx]
        options = (d - 1,) if self._resumable else (d - 1, d, d + 1)
        for target in options:
            print(f"dist {d}")
            # Prefer tiles that are already passable (no road build needed)
            for ni in pnb:
                if dist[ni] != target:
                    continue
                next_pos = Position(ni % w, ni // w)
                direction = pos.direction_to(next_pos)
                if ct.can_move(direction):
                    ct.move(direction)
                    return True
            # Fall back to building a road
            for ni in pnb:
                if dist[ni] != target:
                    continue
                next_pos = Position(ni % w, ni // w)
                direction = pos.direction_to(next_pos)
                if ct.can_build_road(next_pos):
                    ct.build_road(next_pos)
                if ct.can_move(direction):
                    ct.move(direction)
                    return True
        return False
