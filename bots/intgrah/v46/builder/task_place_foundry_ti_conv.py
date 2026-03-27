"""Replace a Ti conveyor carrying mixed Ti+Ax flow with a foundry.

Detects a conveyor with both Ti and Ax flow. Navigates there and replaces
it with a foundry. The foundry consumes min(Ti, Ax) and outputs RAx
downstream through the existing chain.

This is Method 1 of RAx refining: the foundry directly replaces a conveyor
on the Ti chain, breaking the Ti passthrough but producing RAx instead.
"""

from building import BuildingArmouredConveyor, BuildingConveyor
from cambc import Controller, Direction, Position

from .build import Action, PlaceFoundry
from .helpers import cardinal_adjacent, move_toward_with_road
from .state import State


def place_foundry_ti_conv(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    pos = state.pos
    f = state.my_flow
    best_tile: Position | None = None
    best_score = 0.0
    best_dist = 999999

    for p in state.my_transport:
        i = state.idx(p.x, p.y)
        bld = state.building[i]
        match bld:
            case BuildingConveyor() | BuildingArmouredConveyor():
                pass
            case _:
                continue
        ti_f = f.ti[i]
        ax_f = f.ax[i]
        if ti_f <= 0 or ax_f <= 0:
            continue
        score = min(ti_f, ax_f)
        dist = (pos.x - p.x) ** 2 + (pos.y - p.y) ** 2
        if score > best_score or (score == best_score and dist < best_dist):
            best_score = score
            best_dist = dist
            best_tile = p

    if best_tile is None:
        return None

    target = best_tile

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
