"""Navigate to unharvested Ti ore and place a harvester.

If the builder is already cardinally adjacent to Ti ore, it places the
harvester immediately. Otherwise, it navigates to the nearest unharvested
Ti ore, sorted by Euclidean distance, skipping claimed and enemy-occupied
tiles. If the move places the builder adjacent to the ore, it places the
harvester in the same turn (move + build).
"""

from cambc import Controller, Direction, Position
from marker import MarkerTaskClaim, TaskKind

from .build import Action, PlaceHarvester
from .helpers import cardinal_adjacent, is_claimed, move_toward_with_road
from .state import State


def harvest_ti(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    pos = state.pos
    unharvested = state.ore_ti - state.my_harvested - state.en_harvested
    if not unharvested:
        return None

    for ddx, ddy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        p = (pos.x + ddx, pos.y + ddy)
        if p in unharvested:
            ore_pos = Position(p[0], p[1])
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

    w = state.w
    rnd = ct.get_current_round()
    candidates = sorted(
        unharvested,
        key=lambda o: (pos.x - o[0]) ** 2 + (pos.y - o[1]) ** 2,
    )
    for ore in candidates:
        oi = ore[1] * w + ore[0]
        bld = state.building[oi]
        if bld is not None and bld.team != state.my_team:
            continue
        if is_claimed(state, oi, TaskKind.NAV_ORE):
            continue
        adj = cardinal_adjacent(state, pos, Position(ore[0], ore[1]))
        if adj is None:
            continue
        move, build = move_toward_with_road(state, ct, adj)
        if move != Direction.CENTRE and build is None:
            new_pos = pos.add(move)
            ore_pos = Position(ore[0], ore[1])
            if new_pos.distance_squared(ore_pos) == 1:
                bid = ct.get_tile_building_id(ore_pos)
                if bid is not None and ct.can_destroy(ore_pos):
                    ct.destroy(ore_pos)
                h_cost, _ = ct.get_harvester_cost()
                ti, _ = ct.get_global_resources()
                if ti >= h_cost:
                    build = PlaceHarvester(ore_pos)
        state.claim = MarkerTaskClaim(TaskKind.NAV_ORE, oi, rnd)
        state.debug_target = (Position(ore[0], ore[1]), 0, 255, 0)
        return move, build
    return None
