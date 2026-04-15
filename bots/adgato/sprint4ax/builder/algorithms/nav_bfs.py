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

from cambc import Controller, EntityType, Environment, Position

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

_BUDGET = 1729


def _bfs_compute(
    pnb_push: list[list[int]],
    pnb_set: list[list[int]],
    dist: list[int],
    q: list[int],
    cur_idx: int,
    ct: Controller,
) -> bool:
    """Resumable backwards BFS. Returns True when finished.

    Finished means the agent tile has been reached (one level past it)
    or the queue is exhausted. False means we bailed on CPU budget;
    call again with the same q to resume.

    On exit, stale (already-processed) entries are trimmed from q so
    the next call picks up where we left off.
    """
    # Stop at the agent.
    qi = 0
    q_append = q.append
    cpu_time = ct.get_cpu_time_elapsed
    for node in q:
        if node == cur_idx:
            del q[:qi]
            return True
        d = dist[node] + 1
        for ni in pnb_push[node]:
            if d < dist[ni]:
                dist[ni] = d
                q_append(ni)
        for ni in pnb_set[node]:
            if d < dist[ni]:
                dist[ni] = d
                if ni == cur_idx:
                    q_append(ni)
        qi += 1
        if cpu_time() > _BUDGET:
            del q[:qi]
            return False
    q.clear()
    return True


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
        self.w = w
        self.h = h
        pw = w + 2
        self.pw = pw
        self.rn = w * h
        n = pw * (h + 2)
        self.n = n

        # passable grid: border = 0, interior = 2 (unseen, treated as
        # passable by truthy checks but distinguishable from observed-
        # passable = 1).
        self.passable: list[int] = [2] * n
        row_data = [0] * pw
        self.passable[0:pw] = row_data
        self.passable[(h + 1) * pw : (h + 1) * pw + pw] = row_data
        for ry in range(1, h + 1):
            self.passable[ry * pw] = 0
            self.passable[ry * pw + pw - 1] = 0

        self.pnb_push: list[list[int]] = [[]] * n
        self.pnb_set: list[list[int]] = [[]] * n
        self._pnb_dirty: set[int] = set()
        self._pnb_init_progress: int = 0

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

    @property
    def ready(self) -> bool:
        """True once the initial pnb build has finished."""
        return self._pnb_init_progress >= self.rn

    def real_to_padded(self, i: int) -> int:
        """Convert a real `y * w + x` index to a padded index."""
        return i + 2 * (i // self.w) + self.pw + 1

    def padded_to_real(self, pi: int) -> int:
        """Convert a padded index back to a real `y * w + x` index."""
        return (pi // self.pw - 1) * self.w + (pi % self.pw - 1)

    def update_tile(
        self,
        i: int,
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
        self.set_passable(i, passable=passable)

    def set_passable(self, i: int, *, passable: bool) -> None:
        """Write passability, mark pnb dirty, notify navs of a change."""
        pi = self.real_to_padded(i)
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

    def init_pnb_chunk(self, ct: Controller) -> bool:
        """Build pnb tables assuming every real tile is passable.

        Runs incrementally, yielding every 256 tiles when the caller's
        budget is exhausted. Returns True once complete.
        """
        w = self.w
        pw = self.pw
        pnb_push = self.pnb_push
        pnb_set = self.pnb_set
        progress = self._pnb_init_progress
        total = self.rn

        ne_off, se_off, sw_off, nw_off, n_off, e_off, s_off, w_off = self.offsets

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
            if progress & 255 == 0 and ct.get_cpu_time_elapsed() > _BUDGET:
                self._pnb_init_progress = progress
                return False

        self._pnb_init_progress = total
        return True

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
        self._dist: list[int] = [INF] * n

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
        dist = self._dist
        dist[:] = [INF] * grid.n
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
        pw = grid.pw
        my_bbid = ct.get_id()
        ci = (start.y + 1) * pw + (start.x + 1)
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
        best_d = INF
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
        if best_d >= INF:
            return None
        return Position(start.x + best_dx, start.y + best_dy)

    def search(
        self,
        ct: Controller,
        start: Position,
        goals: list[Position],
    ) -> Position | None:
        grid = self.grid
        pw = grid.pw

        # Finish the initial pnb build if it isn't done yet. On the
        # first few turns the bot spends budget here; until pnb is
        # ready BFS can't run.
        if not grid.ready:
            grid.init_pnb_chunk(ct)
            if ct.get_cpu_time_elapsed() > _BUDGET:
                return None

        # Apply any passability changes accumulated since last turn.
        if grid.has_dirty_pnb:
            grid.rebuild_pnb()

        if ct.get_move_cooldown() > 0:
            return None

        self.set_goal(goals)

        self._cur_idx = (start.y + 1) * pw + (start.x + 1)

        if self._dirty:
            self._restart()
            self._dirty = False
        elif not self._resumable and self._dist[self._cur_idx] >= INF and self._q:
            self._resumable = True

        if self._resumable:
            _bfs_compute(
                grid.pnb_push, grid.pnb_set, self._dist, self._q, self._cur_idx, ct
            )
            self._resumable = bool(self._q)

        cd = self._dist[self._cur_idx]
        self._cur_dist = cd if cd < INF else -1
        if self._cur_dist < 0:
            return None

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

        pos = self.my_pos
        pi = (pos.y + 1) * pw + (pos.x + 1)
        d = dist[pi]
        if d >= INF:
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
                if dist[ni] == 0:
                    return Position(ni % pw - 1, ni // pw - 1)
            return None
        return Position(pi % pw - 1, pi // pw - 1)
