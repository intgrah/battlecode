"""DO NOT USE

Raid enemy transport by walking onto it and attacking.

The builder navigates to the highest-flow enemy transport tile, walks onto
it, and uses the attack action (2 Ti for 2 damage). Targets conveyors,
bridges, and splitters. Self-destruct damage was removed in the balance
patch — only the attack action works now.
"""

from cambc import Controller, Direction, EntityType, Position

from .build import Action, SelfDestruct
from .helpers import move_toward
from .state import State

_RAIDABLE = frozenset((EntityType.CONVEYOR, EntityType.BRIDGE, EntityType.SPLITTER))


def raid(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    best_tile = None
    best_flow = 0.0
    w = state.w
    for i in state.en_transport:
        if state.en_flow.total[i] <= 0:
            continue
        ent = state.entity[i]
        if ent is None or ent[0] not in _RAIDABLE:
            continue
        if i in state.unit_tiles:
            continue
        if state.en_flow.total[i] > best_flow:
            best_flow = state.en_flow.total[i]
            best_tile = (i % w, i // w)
    if best_tile is None:
        return None
    target = Position(best_tile[0], best_tile[1])
    pos = state.pos
    if pos == target:
        return Direction.CENTRE, SelfDestruct(pos)
    move = move_toward(state, ct, target)
    state.debug_target = (target, 255, 0, 255)
    return move, None
