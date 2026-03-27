"""Patrol friendly infrastructure.

Navigates to the least-recently-seen tile that has friendly infrastructure
(harvesters, transport, foundries, turrets, or core). Keeps the builder's
belief about its own network fresh and detects enemy disruption.

If the primary target is unreachable, tries up to 3 alternatives sorted
by staleness. Returns None only when no target produces movement.
"""

from cambc import Controller, Direction, Position

from .build import Action
from .helpers import move_toward_with_road
from .state import State

_MAX_PATROL_ATTEMPTS = 3


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
    # Sort by staleness (least-recently-seen first)
    w = state.w
    ranked = sorted(infra, key=lambda i: state.last_seen[i])
    for i in ranked[:_MAX_PATROL_ATTEMPTS]:
        x, y = i % w, i // w
        target = Position(x, y)
        move, build = move_toward_with_road(state, ct, target)
        if move != Direction.CENTRE or build is not None:
            state.debug_target = (target, 255, 255, 0)
            return move, build
    return None
