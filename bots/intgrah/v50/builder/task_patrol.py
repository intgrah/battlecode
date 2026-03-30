"""Patrol friendly infrastructure.

Navigates to the least-recently-seen tile that has friendly infrastructure
(harvesters, transport, foundries, turrets, or core). Keeps the builder's
belief about its own network fresh and detects enemy disruption.
"""

from cambc import Controller, Direction, Position

from .action import Action
from .helpers import move_toward_with_road
from .state import State


def patrol(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    infra = (
        state.my_harvesters
        | state.my_transport
        | state.my_foundries
        | state.my_turrets
        | state.my_core_tiles
    )
    if not infra:
        return None
    best_tile: Position | None = None
    best_freshness = state.age + 1
    for p in infra:
        i = state.idx(p.x, p.y)
        if state.last_seen[i] < best_freshness:
            best_freshness = state.last_seen[i]
            best_tile = p
    if best_tile is None:
        return None
    target = best_tile
    move, build = move_toward_with_road(state, ct, target)
    state.debug_target = (target, 255, 255, 0)
    return move, build
