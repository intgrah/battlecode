"""Padded passability grid with precomputed neighbor tables.

Internal grid is padded by 1 tile on each side (sentinel border).
All border tiles are permanently impassable, so every real tile has
8 valid neighbors — no bounds checks needed anywhere.

Neighbor tables are split into two lists per tile:
- pnb_push: neighbors that must be enqueued during BFS
  (diagonals, plus cardinals whose adjacent diags aren't both passable)
- pnb_set: neighbors whose distance can be written directly
  (cardinals where both adjacent diags are passable — BFS already
  reached them via the diags, so enqueuing is redundant)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import EntityType, Environment, Position
from symmetry import Symmetry, mirror_idx

if TYPE_CHECKING:
    from bfs import NavBfs
    from collections.abc import Callable

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
    """Padded passability grid with incremental neighbor tables."""

    def __init__(self, w: int, h: int) -> None:
        self.navs: list[NavBfs] = []
        self.w = w
        self.h = h
        pw = w + 2
        self.pw = pw
        self.rn = w * h
        n = pw * (h + 2)
        self.n = n

        # Passable grid: border=0, interior=1 (assume all passable initially)
        self.passable: list[int] = [1] * n
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

        # Neighbor offsets (constant for padded grid)
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
        """True once the initial pnb build is complete."""
        return self._pnb_init_progress >= self.rn

    def real_to_padded(self, i: int) -> int:
        """Convert a real tile index to a padded index."""
        return i + 2 * (i // self.w) + self.pw + 1

    def padded_to_real(self, pi: int) -> int:
        """Convert a padded index to a real tile index."""
        return (pi // self.pw - 1) * self.w + (pi % self.pw - 1)

    def update_tile(
        self,
        i: int,
        env: Environment,
        building_type: EntityType | None,
        is_allied_building: bool,
        sym: Symmetry = Symmetry.UNKNOWN,
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

        self.set_passable(i, passable=passable)

        if sym is not Symmetry.UNKNOWN and env == Environment.WALL:
            mi = mirror_idx(i, sym, self.w, self.h)
            self.set_passable(mi, passable=False)

    def set_passable(self, i: int, passable: bool) -> None:
        """Write passability, mark pnb dirty, and notify nav if a closer tile changed."""
        pi = self.real_to_padded(i)

        old = self.passable[pi]
        if old != passable:
            self.passable[pi] = passable
            pnb_dirty = self._pnb_dirty
            if passable:
                pnb_dirty.add(pi)
            else:
                pnb_dirty.discard(pi)
            for off in self.offsets:
                ni = pi + off
                if self.passable[ni]:
                    pnb_dirty.add(ni)
                else:
                    pnb_dirty.discard(ni)
            for nav in self.navs:
                nav.notify_closer_tile_changed(pi)

    def get_passable(self, pos: Position) -> bool:
        """Return passability at a position."""
        pi = (pos.y + 1) * self.pw + (pos.x + 1)
        return self.passable[pi]

    def mirror_known(
        self,
        sym: Symmetry,
        known_env: dict[int, Environment],
    ) -> None:
        """Bulk-mirror walls via symmetry. Only walls are safe to mirror — non-wall
        tiles may have impassable buildings we haven't seen yet."""
        w, h = self.w, self.h
        for i, env in known_env.items():
            if env == Environment.WALL:
                mi = mirror_idx(i, sym, w, h)
                self.set_passable(mi, passable=False)

    def init_pnb_chunk(self, within_budget: Callable[[], bool]) -> bool:
        """Build pnb tables incrementally, assuming all real tiles passable.

        Single loop over real tiles — all have 8 valid padded neighbors.
        Returns True when complete.
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
        """Rebuild pnb for tiles with passability changes."""
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
