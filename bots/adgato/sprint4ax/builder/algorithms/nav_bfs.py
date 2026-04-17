"""Port of adgato/mesh's NavBfs + PassableGrid for v54 movement.

This is kept deliberately close to `bots/adgato/foundry_rush/bfs.py`.
Differences from the source:

- No `symmetry` module imports or mirror helpers — v54 handles
  symmetry in `state_update_map.py` via a different path.
- No `lib.visualiser` import / `emit_vis` method — we don't need
  the debug visualiser overlays here.
- `NavBfs.step` doesn't return the 8-direction-weight tuple that
  adgato's version does. Instead we expose `search` /
  `search_blocked` with the same external contract as v54's
  `MoveHeapAstar`, so it drops into `move_search`.

Everything else — chunked pnb init, dirty-tile invalidation, the
pnb_push / pnb_set split, goal-directed early termination — is
ported intact.
"""

from __future__ import annotations

from typing import Final

from cambc import Controller, EntityType, Environment, Position

_BUDGET: Final[int] = 1729

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
    dist: bytearray,
    frontier: list[int],
    cur_idx: int,
    ct: Controller,
) -> list[int]:
    # Stop at the agent.
    cpu_time = ct.get_cpu_time_elapsed
    budget = _BUDGET
    d = 0
    while frontier:
        next_frontier: list[int] = []
        for node in frontier:
            if node == cur_idx:
                return frontier
            for ni in pnb_push[node]:
                if dist[ni] == 0xFF:
                    dist[ni] = d
                    next_frontier.append(ni)
            for ni in pnb_set[node]:
                if dist[ni] == 0xFF:
                    dist[ni] = d
                if ni == cur_idx:
                    next_frontier.append(ni)
        frontier = next_frontier
        d = (d + 1) & 0xFF
        if d > 5 and cpu_time() > budget:
            return frontier
    return []


class PassableGrid:
    """Padded-by-1 passability grid with incremental neighbour tables.

    - `passable[pi]` is 1 if the tile is walkable, 0 otherwise.
    - `pnb_push[pi]` is the list of padded neighbour indices BFS
      should enqueue when processing `pi`. Diagonals always push,
      plus any cardinal whose adjacent diagonals aren't both
      passable (so the cardinal wouldn't have been reached via the
      diagonals).
    - `pnb_set[pi]` is the list of cardinals that CAN be reached
      via their adjacent diagonals — those just get `dist` set
      directly and don't need to be pushed onto the queue again.
    - Border tiles (index 0, last row, left/right columns) are
      permanently 0 so every interior tile has 8 valid neighbours
      without bounds checks.
    """

    def __init__(self, w: int, h: int) -> None:
        self.navs: list[NavBfs] = []
        pw = w + 2

        self.pw = pw
        n = pw * (h + 2)
        self.n = n

        self.pnb_push: list[list[int]] = [[]] * n
        self.pnb_set: list[list[int]] = [[]] * n
        self._pnb_dirty: set[int] = set()
        self._pnb_init_progress: int = 0
        self.passable: bytearray = bytearray(n)

        # Padded neighbour flat offsets. Order matches adgato so
        # `rebuild_pnb`'s tuple-unpack works the same way.
        self.offsets: tuple[int, ...] = (
            -pw + 1,  # NE
            pw + 1,  # SE
            pw - 1,  # SW
            -pw - 1,  # NW
            -pw,  # N
            1,  # E
            pw,  # S
            -1,  # W
        )
        ne_off, se_off, sw_off, nw_off, n_off, e_off, s_off, w_off = self.offsets

        pnb_push = self.pnb_push
        pnb_set = self.pnb_set
        for y in range(h):
            row_start = (y + 1) * pw + 1
            for x in range(w):
                pi = row_start + x
                pnb_push[pi] = [pi + ne_off, pi + se_off, pi + sw_off, pi + nw_off]
                pnb_set[pi] = [pi + n_off, pi + e_off, pi + s_off, pi + w_off]

    def init(self, w: int, h: int) -> None:

        rpw = w + 2
        pw = self.pw
        self.rn = w * h

        EMPTY: list[int] = []
        pnb_push = self.pnb_push
        pnb_set = self.pnb_set

        row_data = [EMPTY] * rpw
        for arr in (pnb_push, pnb_set):
            arr[0:rpw] = row_data
            arr[(h + 1) * pw : (h + 1) * pw + rpw] = row_data
            for ry in range(1, h + 1):
                arr[ry * pw] = EMPTY
                arr[ry * pw + rpw - 1] = EMPTY

        passable = self.passable
        for y in range(h):
            row_start = (y + 1) * pw + 1
            for x in range(w):
                pi = row_start + x
                passable[pi] = 2

    @property
    def ready(self) -> bool:
        """True once the initial pnb build has finished."""
        return self._pnb_init_progress >= self.rn

    def update_tile(
        self,
        pos: Position,
        env: Environment | None,
        building_type: EntityType | None,
        *,
        is_allied_building: bool,
    ) -> None:
        """Update a single real-tile passability from vision data."""
        if env is None:
            # Unobserved — leave as-is (default 2 until we see it).
            return
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

        pi = (pos.y + 1) * self.pw + pos.x + 1
        self.set_passable(pi, passable=passable)

    def set_passable(self, pi: int, *, passable: bool) -> None:
        """Write passability, mark pnb dirty, notify navs of a change."""
        old = self.passable[pi]
        if old != passable:
            self.passable[pi] = 1 if passable else 0
            # Both old and new truthy (e.g. unseen 2 → observed 1):
            # neighbours unchanged, skip pnb rebuild.
            if old and passable:
                return
            pnb_dirty = self._pnb_dirty
            if passable:
                pnb_dirty.add(pi)
            else:
                pnb_dirty.discard(pi)
            # Mark affected neighbours dirty too — their pnb lists
            # depend on whether this tile is passable.
            for off in self.offsets:
                ni = pi + off
                if self.passable[ni]:
                    pnb_dirty.add(ni)
                else:
                    pnb_dirty.discard(ni)
            for nav in self.navs:
                nav.notify_closer_tile_changed(pi)

    def rebuild_pnb(self) -> None:
        """Rebuild pnb for dirty tiles."""
        passable = self.passable
        pnb_push = self.pnb_push
        pnb_set = self.pnb_set
        ne_off, se_off, sw_off, nw_off, n_off, e_off, s_off, w_off = self.offsets
        for pi in self._pnb_dirty:
            push = pnb_push[pi]
            assign = pnb_set[pi]
            push.clear()
            assign.clear()
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

    def get_passable(self, pos: Position) -> bool:
        """Return passability at a position."""
        pi = (pos.y + 1) * self.pw + (pos.x + 1)
        return bool(self.passable[pi])

    @property
    def has_dirty_pnb(self) -> bool:
        return bool(self._pnb_dirty)


class NavBfs:
    """Backwards-BFS navigation for builder bots (adgato/mesh port).

    Fills a distance field from the goal using the PassableGrid's
    precomputed neighbour tables. Subsequent turns with the same
    goal just scan the bot's 8 neighbours for the lowest dist —
    O(8) per step.
    """

    def __init__(self, grid: PassableGrid) -> None:
        self.grid = grid
        grid.navs.append(self)
        n = grid.n

        self._gis: list[int] = []
        self._dirty = True

        # Distance array. Unvisited tiles hold INF; reset on each restart.
        self._dist_reset: bytearray = bytearray(b"\xff" * n)
        self._dist: bytearray = bytearray(self._dist_reset)

        self._q: list[int] = []
        self._resumable = False
        self._cur_dist = -1
        self._cur_idx = -1

    def mark_dirty(self) -> None:
        """Force a BFS restart on the next call."""
        self._dirty = True

    def notify_closer_tile_changed(self, pi: int) -> None:
        """If the tile at `pi` is closer to the goal than the agent,
        our dist field is stale and we need to restart."""
        if self._dist[pi] < self._cur_dist:
            self._dirty = True

    def set_goal(self, goals: list[Position]) -> None:
        """Replace the goal list. Only marks dirty if the set changed."""
        pw = self.grid.pw
        new_gis = [(g.y + 1) * pw + (g.x + 1) for g in goals]
        if new_gis == self._gis:
            return
        self._gis = new_gis
        self._dirty = True

    def _restart(self) -> None:
        """Reset BFS state for a fresh backward search from goals."""
        grid = self.grid
        self._dist = bytearray(self._dist_reset)
        dist = self._dist
        passable = grid.passable
        offsets = grid.offsets
        q = self._q
        q.clear()
        for gi in self._gis:
            dist[gi] = 0
            if passable[gi]:
                q.append(gi)
            else:
                # Impassable goal (e.g. barrier, enemy building): seed
                # passable neighbours at dist=1 so the bot can path to
                # an adjacent tile.
                for off in offsets:
                    ni = gi + off
                    if passable[ni] and dist[ni] > 1:
                        dist[ni] = 1
                        q.append(ni)
        self._resumable = True

    def _best_step(self, ct: Controller, start: Position) -> Position | None:
        """Scan the agent's 8 neighbours in the padded grid and pick
        the one with the lowest BFS dist. Breaks ties by step order
        in `grid.offsets` (deterministic)."""
        grid = self.grid
        dist = self._dist
        passable = grid.passable
        my_bbid = ct.get_id()
        ci = self._cur_idx
        # Direction deltas aligned with grid.offsets order:
        # NE, SE, SW, NW, N, E, S, W.
        deltas = (
            (1, -1),
            (1, 1),
            (-1, 1),
            (-1, -1),
            (0, -1),
            (1, 0),
            (0, 1),
            (-1, 0),
        )
        best_d = 0xFF
        best_dx = 0
        best_dy = 0
        for off, (dx, dy) in zip(grid.offsets, deltas, strict=False):
            ni = ci + off
            if not passable[ni]:
                continue
            d = dist[ni]
            pos = Position(start.x + dx, start.y + dy)
            bbid = ct.get_tile_builder_bot_id(pos)
            if bbid is not None and bbid != my_bbid:
                continue
            if d < best_d or (d == best_d and ct.is_tile_passable(pos)):
                best_d = d
                best_dx = dx
                best_dy = dy
        if best_d >= 0xFF:
            return None
        return Position(start.x + best_dx, start.y + best_dy)

    def search(
        self,
        ct: Controller,
        start: Position,
        goals: list[Position],
    ) -> Position | None:
        grid = self.grid

        # Apply any passability changes accumulated since last turn.
        if grid.has_dirty_pnb:
            grid.rebuild_pnb()

        if ct.get_move_cooldown() > 0:
            return None

        self._cur_idx = (start.y + 1) * self.grid.pw + (start.x + 1)
        self.set_goal(goals)

        if self._cur_idx in self._gis:
            return start

        if self._dirty:
            self._restart()
            self._dirty = False
        elif not self._resumable and self._dist[self._cur_idx] >= 0xFF and self._q:
            self._resumable = True

        if self._resumable:
            self._q = _bfs_compute(
                grid.pnb_push, grid.pnb_set, self._dist, self._q, self._cur_idx, ct
            )
            self._resumable = bool(self._q)

        cd = self._dist[self._cur_idx]
        self._cur_dist = cd
        if cd == 0xFF:
            return None
        if not cd:
            # we overflowed path length, cursed fix
            self._dirty = True

        next_step = self._best_step(ct, start)
        if next_step is None:
            return None
        return next_step

    def nearest_goal(self, ct: Controller) -> Position | None:
        """Walk the BFS distance field from the agent toward a goal.

        Follows greedy descent in `_dist` (first 8-neighbor with strictly
        smaller distance). Returns the reached goal `Position` (dist==0).
        Returns None as soon as the next step would land on an unseen
        tile, or no descending neighbor exists.
        """
        pw = self.grid.pw
        passable = self.grid.passable
        dist = self._dist
        offsets = self.grid.offsets

        pos = ct.get_position()
        pi = (pos.y + 1) * pw + (pos.x + 1)
        d = dist[pi]
        if d >= 0xFF:
            return None
        while d > 1:
            for off in offsets:
                ni = pi + off
                dn = dist[ni]
                if dn < d and passable[ni] == 1:
                    pi = ni
                    d = dn
                    break
            else:
                return None
        # d <= 1: either already on the goal (d==0) or one step away.
        # Check neighbors for the actual goal tile (dist==0), which may
        # be impassable (e.g. a barrier).
        if d == 1:
            for off in offsets:
                ni = pi + off
                if not dist[ni]:
                    return Position(ni % pw - 1, ni // pw - 1)
            return None
        return Position(pi % pw - 1, pi // pw - 1)
