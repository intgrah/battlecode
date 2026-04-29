from __future__ import annotations

from itertools import chain
from typing import TYPE_CHECKING

from util.constants import INF, MAX_WIDTH
from util.directions import DIR4

from builder.helpers import make_move

if TYPE_CHECKING:
    from cambc import Controller, Position

    from builder import Builder


def _walkable_anchor(self: Builder, pos: Position) -> Position | None:
    """Bugnav rejects impassable goals. Return `pos` if walkable,
    otherwise the cheapest passable cardinal neighbour."""
    cost_grid = self.cost_grid
    if cost_grid[pos.y * MAX_WIDTH + pos.x] is not INF:
        return pos
    best = None
    best_cost = INF
    for d in DIR4:
        n = pos.add(d)
        if not self.in_bounds(n):
            continue
        c = cost_grid[n.y * MAX_WIDTH + n.x]
        if c is not INF and c < best_cost:
            best_cost = c
            best = n
    return best


def run_patrol(self: Builder, ct: Controller) -> bool:
    """Walk toward the oldest important tile. Important = friendly
    harvesters, foundries, and core. `last_seen` is refreshed in
    `update_patrol` (own vision + one trusted friend's vision), so
    the argmax of `round - last_seen[i]` directs us to whichever
    piece of infra hasn't been watched longest. Tiebreak on distance
    to favour the closer of two equally-stale tiles (avoids
    oscillating between equidistant maxima)."""
    last_seen = self.last_seen
    rnd = self.round
    mx = self.my_pos.x
    my_y = self.my_pos.y

    best_age = -1
    best_dist = 1 << 30
    best_pos = None

    candidates = chain(self.my_harvesters, self.my_foundries)
    if self.my_core is not None:
        candidates = chain(candidates, (self.my_core,))
    for pos in candidates:
        age = rnd - last_seen[pos.y * MAX_WIDTH + pos.x]
        if age < best_age:
            continue
        dx = pos.x - mx
        dy = pos.y - my_y
        d = dx * dx + dy * dy
        if age > best_age or d < best_dist:
            best_age = age
            best_dist = d
            best_pos = pos

    self.patrol_head = best_pos
    if best_pos is None:
        return False
    anchor = _walkable_anchor(self, best_pos)
    if anchor is None:
        return False
    make_move(self, ct, anchor)
    return True
