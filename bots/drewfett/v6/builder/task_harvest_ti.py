"""Navigate to unharvested Ti ore and place a harvester.

Simple approach: score ore by walk distance + connection distance,
with a small bonus for ore toward the enemy half. Walk to ore, place
harvester when adjacent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Controller, Direction, Environment, Position
from marker import MarkerTaskClaim, TaskKind
from util import DIR4_DELTA, INF

from building import BuildingBarrier, BuildingGunner, BuildingMarker, BuildingRoad, BuildingSentinel
from .action import Action, PlaceBarrier, PlaceGunner, PlaceHarvester, PlaceRoad, PlaceSentinel, PlaceSplitter
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

    # Secure harvesters that have a conveyor connected
    # Layout: conveyor—harvester—gunner (opposite), barrier on a side
    for hi in state.my_harvesters:
        hx, hy = hi % w, hi // w
        harv_pos = Position(hx, hy)
        if pos.distance_squared(harv_pos) > 8:
            continue

        # Find the conveyor feeding this harvester
        conv_dir: tuple[int, int] | None = None
        has_gunner = False
        has_barrier = False

        from building import BuildingConveyor, BuildingSplitter, BuildingArmouredConveyor
        for ddx, ddy in DIR4_DELTA:
            nx, ny = hx + ddx, hy + ddy
            if not state.in_bounds(nx, ny):
                continue
            ni = ny * w + nx
            bld = state.building[ni]
            match bld:
                case BuildingConveyor(team=team) | BuildingArmouredConveyor(team=team) | BuildingSplitter(team=team) if team == state.my_team:
                    conv_dir = (ddx, ddy)
                case BuildingGunner(team=team) if team == state.my_team:
                    has_gunner = True
                case BuildingBarrier(team=team) if team == state.my_team:
                    has_barrier = True

        # Only defend if we have a conveyor connected
        if conv_dir is None:
            continue

        # TODO: re-enable sentinel defense when we can afford it
        _DEFEND_HARVESTERS = False
        if not _DEFEND_HARVESTERS:
            continue

        cdx, cdy = conv_dir
        # The conveyor adjacent to harvester — upgrade to splitter if not already
        cx, cy = hx + cdx, hy + cdy
        ci = cy * w + cx
        cbld = state.building[ci]
        from building import BuildingConveyor, BuildingSplitter, BuildingArmouredConveyor

        needs_splitter = isinstance(cbld, (BuildingConveyor, BuildingArmouredConveyor)) and cbld.team == state.my_team
        is_splitter = isinstance(cbld, BuildingSplitter) and cbld.team == state.my_team

        if needs_splitter and not has_gunner:
            conv_pos = Position(cx, cy)
            if pos.distance_squared(conv_pos) <= 2:
                sp_cost, _ = ct.get_splitter_cost()
                ti_res, _ = ct.get_global_resources()
                if ti_res >= sp_cost:
                    # Splitter faces away from harvester (back receives from harvester)
                    from .task_rush import _find_splitter_dir
                    sp_dir = _find_splitter_dir(state, cx, cy)
                    if sp_dir is None:
                        # Default: face away from harvester
                        from util import DELTA_TO_DIR
                        sp_dir = DELTA_TO_DIR.get((cdx, cdy))
                    if sp_dir is not None:
                        if ct.can_destroy(conv_pos):
                            ct.destroy(conv_pos)
                        if ct.can_build_splitter(conv_pos, sp_dir):
                            return Direction.CENTRE, PlaceSplitter(conv_pos, sp_dir)

        # Place sentinel on a splitter side output
        has_sentinel = False
        if is_splitter:
            sdx, sdy = cbld.direction.delta()
            for odx, ody in [(-sdy, sdx), (sdy, -sdx)]:
                sx, sy = cx + odx, cy + ody
                if state.in_bounds(sx, sy):
                    si = sy * w + sx
                    if isinstance(state.building[si], BuildingSentinel) and state.building[si].team == state.my_team:
                        has_sentinel = True

        if is_splitter and not has_sentinel:
            sdx, sdy = cbld.direction.delta()
            for odx, ody in [(-sdy, sdx), (sdy, -sdx)]:
                sx, sy = cx + odx, cy + ody
                if not state.in_bounds(sx, sy):
                    continue
                si = sy * w + sx
                env = state.env[si]
                if env in (Environment.WALL, Environment.ORE_TITANIUM, Environment.ORE_AXIONITE):
                    continue
                sbld = state.building[si]
                if sbld is not None and not isinstance(sbld, (BuildingRoad, BuildingMarker)):
                    continue
                sentinel_pos = Position(sx, sy)
                if pos.distance_squared(sentinel_pos) > 2:
                    continue
                s_cost, _ = ct.get_sentinel_cost()
                ti_res, _ = ct.get_global_resources()
                if ti_res < s_cost:
                    continue
                if sbld is not None and ct.can_destroy(sentinel_pos):
                    ct.destroy(sentinel_pos)
                # Face toward harvester area
                facing = sentinel_pos.direction_to(harv_pos)
                if facing == Direction.CENTRE:
                    facing = Direction.NORTH
                if ct.can_build_sentinel(sentinel_pos, facing):
                    return Direction.CENTRE, PlaceSentinel(sentinel_pos, facing)

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
