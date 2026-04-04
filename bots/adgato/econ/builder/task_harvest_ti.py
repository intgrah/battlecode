"""Navigate to unharvested Ti ore and place a harvester.

Simple approach: score ore by walk distance + connection distance,
with a small bonus for ore toward the enemy half. Walk to ore, place
harvester when adjacent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Controller, Direction, Position
from marker import MarkerTaskClaim, TaskKind
from util import DIR4_DELTA, INF

from .action import Action, PlaceHarvester, PlaceRoad
from .helpers import cardinal_adjacent, is_claimed, move_toward_with_road

if TYPE_CHECKING:
    from .state import State


def _enemy_direction(state: State) -> tuple[int, int]:
    """Target point toward likely enemy core."""
    if state.en_core_pos is not None:
        return state.en_core_pos.x, state.en_core_pos.y
    cx, cy = state.my_core.x, state.my_core.y
    return state.w - 1 - cx, state.h - 1 - cy


def harvest_ti(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    pos = state.pos
    w = state.w
    unharvested = state.ore_ti - state.my_harvesters - state.en_harvesters
    if not unharvested:
        return None

    # Immediate: already adjacent to ore -> place harvester
    for ddx, ddy in DIR4_DELTA:
        ni = (pos.y + ddy) * w + (pos.x + ddx)
        if ni in unharvested:
            ore_pos = Position(pos.x + ddx, pos.y + ddy)
            if ore_pos in state.unit_tiles:
                continue
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
            elif ti >= h_cost:
                # Can't build — blocked, remove from ore set
                state.ore_ti.discard(ni)

    # Pick best ore and walk toward it
    return _pick_and_walk(state, ct, unharvested)


def _pick_and_walk(
    state: State,
    ct: Controller,
    unharvested: set[int],
) -> tuple[Direction, Action | None] | None:
    pos = state.pos
    w = state.w
    rnd = ct.get_current_round()
    infra = state.my_core_tiles | state.my_transport
    enemy_x, enemy_y = _enemy_direction(state)
    max_dim = max(state.w, state.h)

    def _score(oi: int) -> int:
        ox, oy = oi % w, oi // w
        walk_dist = max(abs(pos.x - ox), abs(pos.y - oy))
        if infra:
            conn_dist = min(max(abs(ox - i % w), abs(oy - i // w)) for i in infra)
        else:
            conn_dist = INF
        # Small bonus for ore toward enemy half (lower score = better)
        enemy_dist = max(abs(enemy_x - ox), abs(enemy_y - oy))
        enemy_bonus = (max_dim - enemy_dist) // 4
        return walk_dist + conn_dist * 2 - enemy_bonus

    scored = sorted([(s, oi) for oi in unharvested if (s := _score(oi)) is not None])

    for _, oi in scored:
        bld = state.building[oi]
        # Check blocked ore — unblock if we can see it's free now
        ore_p = Position(oi % w, oi // w)
        if oi in state.blocked_ore:
            rnd = state.age + state.birthday
            if state.last_seen[oi] == rnd:
                if bld is None and ore_p not in state.unit_tiles:
                    state.blocked_ore.discard(oi)
                else:
                    continue
            else:
                continue
        # Skip if ore has a building we can't remove
        if bld is not None:
            from building import BuildingHarvester, BuildingMarker, BuildingRoad

            if not isinstance(bld, (BuildingRoad, BuildingMarker, BuildingHarvester)):
                state.blocked_ore.add(oi)
                continue
        # Skip if enemy unit is standing on the ore
        if ore_p in state.unit_tiles:
            state.blocked_ore.add(oi)
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
        # If we'll be adjacent after moving, place harvester in the same turn
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
