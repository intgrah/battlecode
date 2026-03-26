"""Replace a Ti conveyor carrying mixed Ti+Ax flow with a foundry.

Detects a conveyor with both Ti and Ax flow. Navigates there and replaces
it with a foundry. The foundry consumes min(Ti, Ax) and outputs RAx
downstream through the existing chain.

This is Method 1 of RAx refining: the foundry directly replaces a conveyor
on the Ti chain, breaking the Ti passthrough but producing RAx instead.
"""

from cambc import Controller, Direction, EntityType, Position

from .build import Action, PlaceFoundry
from .helpers import cardinal_adjacent, move_toward_with_road
from .state import State


def place_foundry_ti_conv(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    pos = state.pos
    w = state.w
    f = state.my_flow
    best_tile: int | None = None
    best_score = 0.0
    best_dist = 999999

    for i in state.my_transport:
        ent = state.entity[i]
        if ent is None:
            continue
        if ent[0] not in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR):
            continue
        ti_f = f.ti[i]
        ax_f = f.ax[i]
        if ti_f <= 0 or ax_f <= 0:
            continue
        score = min(ti_f, ax_f)
        cx, cy = i % w, i // w
        dist = (pos.x - cx) ** 2 + (pos.y - cy) ** 2
        if score > best_score or (score == best_score and dist < best_dist):
            best_score = score
            best_dist = dist
            best_tile = i

    if best_tile is None:
        return None

    tx, ty = best_tile % w, best_tile // w
    target = Position(tx, ty)

    if pos.distance_squared(target) <= 2 and pos != target:
        state.debug_target = (target, 255, 128, 0)
        return Direction.CENTRE, PlaceFoundry(target)

    adj = cardinal_adjacent(state, pos, target)
    if adj is None:
        return None
    move, build = move_toward_with_road(state, ct, adj)
    if move != Direction.CENTRE and build is None:
        new_pos = pos.add(move)
        if new_pos.distance_squared(target) <= 2 and new_pos != target:
            build = PlaceFoundry(target)
    state.debug_target = (target, 255, 128, 0)
    return move, build
