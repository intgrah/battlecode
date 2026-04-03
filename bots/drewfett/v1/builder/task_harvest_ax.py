"""Navigate to unharvested Ax ore and place a harvester.

Only activates when Ti flow exists in the network, ensuring a future
foundry will have Ti input to pair with the Ax.

Same placement logic as harvest_ti: place immediately if adjacent, or
navigate to nearest and place on arrival.
"""

from cambc import Controller, Direction, Position
from marker import MarkerTaskClaim, TaskKind
from util import DIR4_DELTA

from .action import Action, PlaceHarvester
from .helpers import cardinal_adjacent, is_claimed, move_toward_with_road
from .state import State


def harvest_ax(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    has_ti_flow = any(state.flow.ti[i] > 0 for i in state.my_transport)
    if not has_ti_flow:
        return None

    pos = state.pos
    w = state.w
    unharvested = state.ore_ax - state.my_harvesters - state.en_harvesters
    if not unharvested:
        return None

    for ddx, ddy in DIR4_DELTA:
        ni = (pos.y + ddy) * w + (pos.x + ddx)
        if ni in unharvested:
            ore_pos = Position(pos.x + ddx, pos.y + ddy)
            bid = ct.get_tile_building_id(ore_pos)
            if bid is not None:
                if ct.can_destroy(ore_pos):
                    ct.destroy(ore_pos)
                else:
                    continue
            h_cost, _ = ct.get_harvester_cost()
            ti, _ = ct.get_global_resources()
            if ti >= h_cost and ct.can_build_harvester(ore_pos):
                return Direction.CENTRE, PlaceHarvester(ore_pos)

    rnd = ct.get_current_round()
    candidates = sorted(
        unharvested,
        key=lambda oi: (pos.x - oi % w) ** 2 + (pos.y - oi // w) ** 2,
    )
    for oi in candidates:
        bld = state.building[oi]
        if bld is not None and bld.team != state.my_team:
            continue
        if is_claimed(state, oi, TaskKind.NAV_ORE):
            continue
        ore_pos = Position(oi % w, oi // w)
        adj = cardinal_adjacent(state, pos, ore_pos)
        if adj is None:
            continue
        result = move_toward_with_road(state, ct, adj)
        if result is None:
            continue
        move, build = result
        if move != Direction.CENTRE and build is None:
            new_pos = pos.add(move)
            if new_pos.distance_squared(ore_pos) == 1:
                bid = ct.get_tile_building_id(ore_pos)
                if bid is not None and ct.can_destroy(ore_pos):
                    ct.destroy(ore_pos)
                h_cost, _ = ct.get_harvester_cost()
                ti, _ = ct.get_global_resources()
                if ti >= h_cost:
                    build = PlaceHarvester(ore_pos)
        state.claim = MarkerTaskClaim(TaskKind.NAV_ORE, oi, rnd)
        return move, build
    return None
