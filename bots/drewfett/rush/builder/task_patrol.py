"""Patrol friendly infrastructure.

Navigates to the least-recently-seen tile that has friendly infrastructure
(harvesters, transport, foundries, turrets, or core). Keeps the builder's
belief about its own network fresh and detects enemy disruption.
"""

from cambc import Controller, Direction, Position
from util import INF

from .action import Action
from .helpers import move_toward_with_road
from .state import State


def patrol(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    infra = state.my_transport | state.my_core_tiles
    if not infra:
        return None
    w = state.w
    best_idx = -1
    best_freshness = INF
    for i in infra:
        if state.last_seen[i] < best_freshness:
            best_freshness = state.last_seen[i]
            best_idx = i
    target = Position(best_idx % w, best_idx // w)
    result = move_toward_with_road(state, ct, target)
    if result is None:
        return None
    ct.draw_indicator_line(state.pos, target, 255, 255, 0)
    return result
