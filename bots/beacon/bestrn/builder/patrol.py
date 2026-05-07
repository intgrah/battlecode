"""Translation of `bots/intgrah/v54.7.9/builder/patrol.py`."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Controller, Position
if TYPE_CHECKING:
    from builder import Builder
from builder.helpers import make_move
from util.constants import INF, MAX_WIDTH
from util.debug import debug as log
from util.directions import DIR4
from util.visualiser import auto_wrap_position


def _walkable_anchor(builder, pos):
    """
    Bugnav rejects impassable goals. Return `pos` if walkable,
    otherwise the cheapest passable cardinal neighbour.
    """
    cost_grid = builder.cost_grid
    if cost_grid[int(pos.y) * 50 + int(pos.x)] != 1000000:
        return pos
    best: Position | None = None
    best_cost = 1000000
    for d in DIR4:
        n = pos.add(d)
        if not builder.in_bounds(n):
            continue
        c = cost_grid[int(n.y) * 50 + int(n.x)]
        if c != 1000000 and c < best_cost:
            best_cost = c
            best = n
    return best


def _candidate_iter(builder):
    """
    Important tiles to patrol: harvesters, foundries, the core, plus
    every friendly transport carrying Ti or Ax (the union of
    `ti_upstream` and `ax_upstream` covers conveyor / armoured /
    bridge / splitter tiles that are downstream of a harvester).
    """
    out: list[Position] = []
    out.extend(builder.my_harvesters)
    out.extend(builder.my_foundries)
    out.extend(builder.ti_upstream)
    out.extend(builder.ax_upstream)
    out.append(builder.my_core)
    return out


def _pick_head(builder):
    last_seen = builder.last_seen
    rnd = builder.state.round
    mx = builder.state.my_pos.x
    my_y = builder.state.my_pos.y
    best_key: tuple[int, int, int, int] = (1, 1 << 30, 1 << 30, 1 << 30)
    best_pos: Position | None = None
    for pos in _candidate_iter(builder):
        age = rnd - last_seen[int(pos.y) * 50 + int(pos.x)]
        dx = pos.x - mx
        dy = pos.y - my_y
        d = dx * dx + dy * dy
        key = (-age, d, pos.y, pos.x)
        if key < best_key:
            best_key = key
            best_pos = pos
    return best_pos


def run_patrol(builder, ct):
    """
    Walk toward the oldest important tile. Sticky: keeps the
    previously-chosen `patrol_head` until we reach it (`dist² <= 2`)
    or its `last_seen` advances past a margin, so the bot doesn't
    flip-flop between two harvesters when ages tick at similar rates.

    Important tiles: friendly harvesters, foundries, core, plus all
    friendly transports carrying Ti or Ax. `last_seen` is refreshed in
    `update_patrol` (own vision + one trusted friend's vision).
    """
    rnd = builder.state.round
    head = builder.patrol_head
    h = head
    if h is not None:
        head_age = rnd - builder.last_seen[int(h.y) * 50 + int(h.x)]
        reached = builder.state.my_pos.distance_squared(h) <= 2
        if reached or head_age <= 0:
            args = {}
            args[str("head")] = auto_wrap_position(h)
            log("patrol: head {head} reached / refreshed, repicking", args)
            head = None
    if head is None:
        head = _pick_head(builder)
        h = head
        if h is not None:
            age = rnd - builder.last_seen[int(h.y) * 50 + int(h.x)]
            args = {}
            args[str("head")] = auto_wrap_position(h)
            args[str("age")] = age
            log("patrol: new head {head} (age={age})", args)
    builder.patrol_head = head
    head = head
    if head is None:
        return False
    anchor = _walkable_anchor(builder, head)
    if anchor is None:
        return False
    make_move(builder, ct, anchor)
    return True
