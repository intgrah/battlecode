"""Port of adgato/mesh's NavBfs + PassableGrid for v54 movement.

This is kept deliberately close to `bots/adgato/mesh/bfs.py` and
`bots/adgato/mesh/grid.py`. Differences from the source:

- No `symmetry` module imports or mirror helpers — v54 handles
  symmetry in `state_update_map.py` via a different path.
- No `lib.visualiser` import / `emit_vis` method — we don't need
  the debug visualiser overlays here.
- No multi-goal / range-limited variant support — movement uses a
  single target at a time. `_compute_range` is omitted entirely.
- `NavBfs.step` doesn't return the 8-direction-weight tuple that
  adgato's version does. Instead we expose `search` /
  `search_blocked` with the same external contract as v54's
  `MoveHeapAstar`, so it drops into `move_search`.

Everything else — chunked pnb init, dirty-tile invalidation, the
pnb_push / pnb_set split, generation-counter dist invalidation,
goal-directed early termination — is ported intact.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Controller, EntityType, Environment, Position

if TYPE_CHECKING:
    from collections.abc import Callable

    from builder.state import State

INF = 1_000_000

_TARGET_DRIFT_SQ = 25

_WALKABLE_BUILDINGS: frozenset[EntityType] = frozenset(
    {
        EntityType.ROAD,
        EntityType.CONVEYOR,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.SPLITTER,
        EntityType.BRIDGE,
    },
)


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

        # passable grid: border = 0, interior = 1 (assume walkable
        # until we observe otherwise).
        self.passable: list[int] = [1] * n
        row_data = [0] * pw
        self.passable[0:pw] = row_data
        self.passable[(h + 1) * pw : (h + 1) * pw + pw] = row_data
        for ry in range(1, h + 1):
            self.passable[ry * pw] = 0
            self.passable[ry * pw + pw - 1] = 0

        self.pnb_push: list[list[int]] = [[] for _ in range(n)]
        self.pnb_set: list[list[int]] = [[] for _ in range(n)]
        self._pnb_dirty: set[int] = set()
        self._pnb_init_progress: int = 0

        # Padded neighbour flat offsets. Order matches adgato so
        # `rebuild_pnb`'s tuple-unpack works the same way.
        self.offsets: tuple[int, ...] = (
            -pw + 1,  # NE
            pw + 1,   # SE
            pw - 1,   # SW
            -pw - 1,  # NW
            -pw,      # N
            1,        # E
            pw,       # S
            -1,       # W
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
            # Unobserved — leave as-is (default 1 until we see it).
            return
        if env == Environment.WALL:
            passable = False
        elif building_type is None:
            passable = True
        elif building_type == EntityType.CORE:
            passable = is_allied_building
        elif (
            building_type == EntityType.MARKER
            or building_type in _WALKABLE_BUILDINGS
        ):
            passable = True
        else:
            passable = False
        self.set_passable(i, passable=passable)

    def set_passable(self, i: int, *, passable: bool) -> None:
        """Write passability, mark pnb dirty, notify navs of a change."""
        pi = self.real_to_padded(i)
        old = self.passable[pi]
        if old == passable:
            return
        self.passable[pi] = 1 if passable else 0
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

    def init_pnb_chunk(self, within_budget: Callable[[], bool]) -> bool:
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
            if progress & 255 == 0 and not within_budget():
                self._pnb_init_progress = progress
                return False

        self._pnb_init_progress = total
        return True

    def rebuild_pnb(self) -> None:
        """Rebuild pnb lists for every tile currently in _pnb_dirty."""
        passable = self.passable
        pnb_push = self.pnb_push
        pnb_set = self.pnb_set
        offsets = self.offsets

        for pi in self._pnb_dirty:
            push = pnb_push[pi]
            assign = pnb_set[pi]
            push.clear()
            assign.clear()
            if not passable[pi]:
                continue

            ne, se, sw, nw, n, e, s, w = tuple(pi + off for off in offsets)

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

            # Cardinal only needs enqueuing if BOTH adjacent diagonals
            # can't reach it — otherwise the diagonal wave sets its
            # dist at the same BFS level.
            if passable[n]:
                (assign if has_ne and has_nw else push).append(n)
            if passable[e]:
                (assign if has_ne and has_se else push).append(e)
            if passable[s]:
                (assign if has_se and has_sw else push).append(s)
            if passable[w]:
                (assign if has_sw and has_nw else push).append(w)

        self._pnb_dirty.clear()

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

        self._goals: list[int] = []
        self._dirty = True

        # Fixed-size arrays — avoids reallocating per search.
        self._dist: list[int] = [0] * n
        self._gen: bytearray = bytearray(n)
        self._g: int = 1

        self._q: list[int] = [0] * n
        self._qi = 0
        self._qlen = 0
        self._resumable = False
        self._cur_dist = -1
        self._cur_idx = -1

        # Public-ish state to match `AStarSearch` / `MoveHeapAstar`
        # for drop-in use as `move_search`.
        self._running_target: Position | None = None
        self._prev_target: Position | None = None
        self._no_path = False
        self._prev_no_path = False

    def mark_dirty(self) -> None:
        """Force a BFS restart on the next call."""
        self._dirty = True

    def notify_closer_tile_changed(self, pi: int) -> None:
        """If the tile at `pi` is closer to the goal than the agent,
        our dist field is stale and we need to restart."""
        if (
            self._gen[pi] == self._g
            and self._dist[pi] < self._cur_dist
        ):
            self._dirty = True

    def change_goal(self, goals: list[Position]) -> None:
        """Replace the goal list. Always marks dirty."""
        pw = self.grid.pw
        self._goals = [(g.y + 1) * pw + (g.x + 1) for g in goals]
        self._dirty = True

    def _restart(self) -> None:
        """Reset BFS state for a fresh backward search from goals."""
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

    def _compute(self, within_budget: Callable[[], bool]) -> bool:
        """Run/resume backwards BFS. Returns True if the agent tile
        has been reached (stop one level past it) or the queue is
        exhausted; False if we bailed on CPU budget and want to
        resume on the next call."""
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
        # Stop one level past the agent. If we haven't touched the
        # agent yet `stop_at` starts unbounded.
        cd = dist[cur_idx] if cur_idx >= 0 and gen[cur_idx] == g else -1
        stop_at = cd + 1 if cd != -1 else INF
        while qi < qlen:
            node = q[qi]
            qi += 1
            d = dist[node] + 1
            if node == cur_idx:
                stop_at = d
            if d > stop_at:
                # Already expanded one wave past the agent. Rewind
                # by one so resume keeps this node for later.
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
                self._qi = qi
                self._qlen = qlen
                return False

        self._qi = qi
        self._qlen = qlen
        return True

    def _best_step(self, start: Position) -> Position | None:
        """Scan the agent's 8 neighbours in the padded grid and pick
        the one with the lowest BFS dist. Breaks ties by step order
        in `grid.offsets` (deterministic)."""
        grid = self.grid
        dist = self._dist
        gen = self._gen
        g = self._g
        passable = grid.passable
        pw = grid.pw
        ci = (start.y + 1) * pw + (start.x + 1)
        # Direction deltas aligned with grid.offsets order:
        # NE, SE, SW, NW, N, E, S, W.
        deltas = (
            (1, -1), (1, 1), (-1, 1), (-1, -1),
            (0, -1), (1, 0), (0, 1), (-1, 0),
        )
        best_d = INF
        best_dx = 0
        best_dy = 0
        for off, (dx, dy) in zip(grid.offsets, deltas, strict=False):
            ni = ci + off
            if not passable[ni]:
                continue
            if gen[ni] != g:
                continue
            d = dist[ni]
            if d < best_d:
                best_d = d
                best_dx = dx
                best_dy = dy
        if best_d >= INF:
            return None
        return Position(start.x + best_dx, start.y + best_dy)

    def search(
        self,
        _state: State,
        ct: Controller,
        start: Position,
        target: Position,
    ) -> list[Position] | None:
        """Same contract as `AStarSearch.search`: returns a 2-element
        `[start, next_step]` path or None."""
        grid = self.grid
        pw = grid.pw

        # Finish the initial pnb build if it isn't done yet. On the
        # first few turns the bot spends budget here; until pnb is
        # ready BFS can't run.
        if not grid.ready:
            grid.init_pnb_chunk(lambda: ct.get_cpu_time_elapsed() < 1729)
            return None

        # Apply any passability changes accumulated since last turn.
        if grid.has_dirty_pnb:
            grid.rebuild_pnb()

        # Update the goal if it changed.
        goal_pi = (target.y + 1) * pw + (target.x + 1)
        if not self._goals or self._goals[0] != goal_pi:
            self._goals = [goal_pi]
            self._dirty = True

        self._cur_idx = (start.y + 1) * pw + (start.x + 1)

        if self._dirty:
            self._restart()
            self._dirty = False
        elif (
            not self._resumable
            and self._gen[self._cur_idx] != self._g
            and self._qi < self._qlen
        ):
            self._resumable = True

        if self._resumable:
            finished = self._compute(
                lambda: ct.get_cpu_time_elapsed() < 1729,
            )
            if finished:
                self._resumable = self._qi < self._qlen

        self._cur_dist = (
            self._dist[self._cur_idx]
            if self._gen[self._cur_idx] == self._g
            else -1
        )
        self._running_target = target
        self._prev_target = target
        if self._cur_dist < 0:
            self._no_path = True
            self._prev_no_path = True
            return None

        next_step = self._best_step(start)
        if next_step is None:
            self._no_path = True
            self._prev_no_path = True
            return None
        self._no_path = False
        self._prev_no_path = False
        return [start, next_step]

    def search_blocked(
        self,
        state: State,
        ct: Controller,
        start: Position,
        goal: Position,
    ) -> list[Position] | None:
        """Same contract as `AStarSearch.search_blocked`: skip tiles
        occupied by other friendly builders when choosing the step.
        DOES NOT force a BFS restart — occupied tiles are only
        filtered at step selection time, so the dist field stays
        valid across turns."""
        # For now, treat `search_blocked` as plain `search`. v54's
        # old bucket A* did a full reset per blocked call which
        # broke incremental BFS; we want the opposite (keep dist
        # field alive, skip bot-occupied tiles only in `_best_step`).
        result = self.search(state, ct, start, goal)
        if result is None:
            return None
        # Post-filter: if the chosen next step is occupied by a
        # friendly bot other than us, try the second-best neighbour.
        _, next_step = result
        bid = ct.get_tile_builder_bot_id(next_step)
        if bid is None or bid == ct.get_id():
            return result
        # Occupied — try the remaining neighbours.
        alt = self._best_step_avoiding(start, next_step, ct)
        if alt is None:
            return None
        return [start, alt]

    def _best_step_avoiding(
        self,
        start: Position,
        skip: Position,
        ct: Controller,
    ) -> Position | None:
        """Re-scan neighbours, excluding `skip` and any other
        friendly-bot occupied tiles."""
        grid = self.grid
        dist = self._dist
        gen = self._gen
        g = self._g
        passable = grid.passable
        pw = grid.pw
        my_id = ct.get_id()
        ci = (start.y + 1) * pw + (start.x + 1)
        deltas = (
            (1, -1), (1, 1), (-1, 1), (-1, -1),
            (0, -1), (1, 0), (0, 1), (-1, 0),
        )
        best_d = INF
        best_dx = 0
        best_dy = 0
        for off, (dx, dy) in zip(grid.offsets, deltas, strict=False):
            ni = ci + off
            if not passable[ni]:
                continue
            if gen[ni] != g:
                continue
            cand = Position(start.x + dx, start.y + dy)
            if cand == skip:
                continue
            bid = ct.get_tile_builder_bot_id(cand)
            if bid is not None and bid != my_id:
                continue
            d = dist[ni]
            if d < best_d:
                best_d = d
                best_dx = dx
                best_dy = dy
        if best_d >= INF:
            return None
        return Position(start.x + best_dx, start.y + best_dy)

    @property
    def no_path(self) -> bool:
        return self._prev_no_path
