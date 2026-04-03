"""Find unharvested titanium ore and place a harvester."""

from __future__ import annotations

from typing import TYPE_CHECKING

from action import PlaceHarvester
from cambc import Position
from marker import ClaimKind, MarkerClaim
from turn import ActionOnly, Turn
from util import INF

from ._helpers import cardinal_adjacent_free, chebyshev, is_claimed, move_toward

if TYPE_CHECKING:
    from cambc import Controller
    from state import State


def run(state: State, ct: Controller) -> Turn | None:
    pos = state.pos
    w = state.w
    rnd = ct.get_current_round()

    # Tiles that have ore but no harvester from either team
    unharvested = state.ore_ti - state.my_harvesters - state.en_harvesters

    if not unharvested:
        return None

    # Infrastructure tiles for connection distance scoring
    infra = state.my_transport | state.my_harvesters | state.my_core_tiles

    best_score = INF
    best_idx: int | None = None

    for oi in unharvested:
        if oi in state.blocked_ore:
            continue
        if is_claimed(state, oi, ClaimKind.NAV_ORE):
            continue

        ox, oy = oi % w, oi // w
        walk_dist = chebyshev(pos.x, pos.y, ox, oy)

        # Connection distance: minimum Chebyshev distance to any infrastructure tile
        conn_dist = INF
        for ii in infra:
            d = chebyshev(ox, oy, ii % w, ii // w)
            if d < conn_dist:
                conn_dist = d
                if d == 0:
                    break

        score = walk_dist + conn_dist * 2
        if score < best_score:
            best_score = score
            best_idx = oi

    if best_idx is None:
        return None

    ore_x, ore_y = best_idx % w, best_idx // w
    ore_pos = Position(ore_x, ore_y)

    # If adjacent to ore and can afford: place harvester
    if (
        pos.distance_squared(ore_pos) <= 2
        and pos != ore_pos
        and ct.can_build_harvester(ore_pos)
    ):
        state.claim = MarkerClaim(ClaimKind.NAV_ORE, best_idx, rnd)
        return ActionOnly(PlaceHarvester(ore_pos))

    # Find a free cardinal-adjacent tile to the ore and walk there
    stand_tile = cardinal_adjacent_free(state, pos, ore_pos)
    if stand_tile is None:
        return None

    state.claim = MarkerClaim(ClaimKind.NAV_ORE, best_idx, rnd)
    return move_toward(state, ct, stand_tile)
