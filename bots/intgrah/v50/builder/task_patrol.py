"""Patrol friendly infrastructure.

Navigates to the least-recently-seen tile that has friendly infrastructure
(harvesters, transport, foundries, turrets, or core). Keeps the builder's
belief about its own network fresh and detects enemy disruption.
"""

from action import Turn
from cambc import Controller, Position
from util import INF

from .helpers import move_toward_with_road
from .state import State


def patrol(
    state: State,
    ct: Controller,
) -> Turn | None:
    infra = state.my_transport | state.my_core_tiles
    # TO DO: assert that all of these tiles are walkable
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
    print(
        f"    patrol: target=({target.x},{target.y}) stale={state.age + state.birthday - best_freshness}"
    )
    ct.draw_indicator_line(state.pos, target, 255, 255, 0)
    return result
