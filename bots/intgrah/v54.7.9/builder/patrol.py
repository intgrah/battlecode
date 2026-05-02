from __future__ import annotations

from itertools import chain
from typing import TYPE_CHECKING

from util.constants import INF, MAX_WIDTH
from util.debug import debug as log
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


def _candidate_set(self: Builder) -> object:
    """Important tiles to patrol: harvesters, foundries, the core, plus
    every friendly transport carrying Ti or Ax (the union of
    `ti_upstream` and `ax_upstream` covers conveyor / armoured /
    bridge / splitter tiles that are downstream of a harvester)."""
    parts = chain(
        self.my_harvesters,
        self.my_foundries,
        self.ti_upstream,
        self.ax_upstream,
    )
    if self.my_core is not None:
        parts = chain(parts, (self.my_core,))
    return parts


def _pick_head(self: Builder) -> Position | None:
    last_seen = self.last_seen
    rnd = self.round
    mx = self.my_pos.x
    my_y = self.my_pos.y
    best_age = -1
    best_dist = 1 << 30
    best_pos = None
    for pos in _candidate_set(self):
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
    return best_pos


def run_patrol(self: Builder, ct: Controller) -> bool:
    """Walk toward the oldest important tile. Sticky: keeps the
    previously-chosen `patrol_head` until we reach it (`dist² <= 2`)
    or its `last_seen` advances past a margin, so the bot doesn't
    flip-flop between two harvesters when ages tick at similar rates.

    Important tiles: friendly harvesters, foundries, core, plus all
    friendly transports carrying Ti or Ax. `last_seen` is refreshed in
    `update_patrol` (own vision + one trusted friend's vision)."""
    last_seen = self.last_seen
    rnd = self.round

    head = self.patrol_head
    if head is not None:
        head_age = rnd - last_seen[head.y * MAX_WIDTH + head.x]
        reached = self.my_pos.distance_squared(head) <= 2
        if reached or head_age <= 0:
            log("patrol: head {head} reached / refreshed, repicking", head=head)
            head = None

    if head is None:
        head = _pick_head(self)
        if head is not None:
            log(
                "patrol: new head {head} (age={age})",
                head=head,
                age=rnd - last_seen[head.y * MAX_WIDTH + head.x],
            )

    self.patrol_head = head
    if head is None:
        return False
    anchor = _walkable_anchor(self, head)
    if anchor is None:
        return False
    make_move(self, ct, anchor)
    return True
