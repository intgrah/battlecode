"""Navigate to unharvested Ax ore and place a harvester.

Only activates when Ti flow exists in the network, ensuring a future
foundry will have Ti input to pair with the Ax.

Same placement logic as harvest_ti: place immediately if adjacent, or
navigate to nearest and place on arrival.
"""

from action import ActionOnly, MoveAction, MoveOnly, PlaceHarvester, Turn
from cambc import Controller, Position
from marker import MarkerTaskClaim, TaskKind

from .helpers import (
    is_claimed,
    min_adjacent_dist,
    move_toward_with_road,
    nearest_reachable_around,
)
from .state import State


def harvest_ax(
    state: State,
    ct: Controller,
) -> Turn | None:
    has_ti_flow = any(state.flow.ti[i] > 0 for i in state.my_transport)
    if not has_ti_flow:
        return None

    pos = state.pos
    w = state.w
    unharvested = state.ore_ax - state.my_harvesters - state.en_harvesters
    if not unharvested:
        return None

    rnd = ct.get_current_round()
    candidates = sorted(
        (oi for oi in unharvested if min_adjacent_dist(state, oi) != -1),
        key=lambda oi: min_adjacent_dist(state, oi),
    )
    for oi in candidates:
        bld = state.building[oi]
        if bld is not None and bld.team != state.my_team:
            continue
        if is_claimed(state, oi, TaskKind.NAV_ORE):
            continue
        ore_pos = Position(oi % w, oi // w)

        if pos.distance_squared(ore_pos) <= 2:
            bid = ct.get_tile_building_id(ore_pos)
            if bid is not None:
                if ct.can_destroy(ore_pos):
                    ct.destroy(ore_pos)
                else:
                    continue
            h_cost, _ = ct.get_harvester_cost()
            ti, _ = ct.get_global_resources()
            if ti >= h_cost and ct.can_build_harvester(ore_pos):
                state.claim = MarkerTaskClaim(TaskKind.NAV_ORE, oi, rnd)
                print(f"    harvest_ax: place at ({ore_pos.x},{ore_pos.y})")
                return ActionOnly(PlaceHarvester(ore_pos))
            continue

        adj = nearest_reachable_around(state, ore_pos)
        if adj is None:
            continue
        result = move_toward_with_road(state, ct, adj)
        if result is None:
            continue
        match result:
            case MoveOnly(move):
                new_pos = pos.add(move)
                if new_pos.distance_squared(ore_pos) <= 2:
                    bid = ct.get_tile_building_id(ore_pos)
                    if bid is not None and ct.can_destroy(ore_pos):
                        ct.destroy(ore_pos)
                    h_cost, _ = ct.get_harvester_cost()
                    ti, _ = ct.get_global_resources()
                    if ti >= h_cost:
                        result = MoveAction(move, PlaceHarvester(ore_pos))
        state.claim = MarkerTaskClaim(TaskKind.NAV_ORE, oi, rnd)
        print(
            f"    harvest_ax: nav to ore ({ore_pos.x},{ore_pos.y}) via ({adj.x},{adj.y})"
        )
        return result
    return None
