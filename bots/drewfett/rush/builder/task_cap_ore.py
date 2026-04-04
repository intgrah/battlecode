"""Cap unclaimed ore nearby by barriering it — denies enemy harvesting.

Only targets ore within a short distance of the builder (opportunistic,
not worth a detour). Skips ore that's already barriered/harvested.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Controller, Direction, Position

from .action import Action, PlaceBarrier
from .helpers import move_toward_with_road

if TYPE_CHECKING:
    from .state import State

_MAX_DETOUR_SQ = 8  # only cap ore within d²≤8 (nearby, not a big detour)


def cap_ore(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    b_cost, _ = ct.get_barrier_cost()
    ti, _ = ct.get_global_resources()
    if ti < b_cost:
        return None

    w = state.w
    pos = state.pos

    # Find nearest unclaimed ore on our half that's close to us
    best: Position | None = None
    best_dist = _MAX_DETOUR_SQ + 1

    unclaimed = (
        state.ore_ti - state.my_harvesters - state.en_harvesters - state.barriers
    )
    for oi in unclaimed:
        bld = state.building[oi]
        if bld is not None:
            continue  # has some building already
        ox, oy = oi % w, oi // w
        dist = (pos.x - ox) ** 2 + (pos.y - oy) ** 2
        if dist >= best_dist:
            continue
        # Only cap ore on enemy half (with slack)
        if state.en_core_pos is not None:
            en_dist = (ox - state.en_core_pos.x) ** 2 + (oy - state.en_core_pos.y) ** 2
            my_dist = (ox - state.my_core.x) ** 2 + (oy - state.my_core.y) ** 2
            if en_dist > my_dist + 20:  # well on our half — econ will handle it
                continue
        best_dist = dist
        best = Position(ox, oy)

    if best is None:
        return None

    if pos.distance_squared(best) <= 2 and pos != best:
        if ct.can_build_barrier(best):
            return Direction.CENTRE, PlaceBarrier(best)

    return move_toward_with_road(state, ct, best)
