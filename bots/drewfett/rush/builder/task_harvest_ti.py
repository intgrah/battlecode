"""Navigate to unharvested Ti ore and place a harvester.

Simple approach: score ore by walk distance + connection distance,
with a small bonus for ore toward the enemy half. Walk to ore, place
harvester when adjacent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingBarrier,
    BuildingGunner,
    BuildingMarker,
    BuildingRoad,
    BuildingSentinel,
)
from cambc import Controller, Direction, Environment, Position
from marker import MarkerTaskClaim, TaskKind
from util import DIR4_DELTA, INF

from .action import (
    Action,
    PlaceHarvester,
    PlaceSentinel,
    PlaceSplitter,
)
from .helpers import cardinal_adjacent, is_claimed, move_toward_with_road

if TYPE_CHECKING:
    from .state import State


def _adjacent_safe_for_harvester(state: State, ox: int, oy: int) -> bool:
    """Check that no enemy transport is adjacent to ore — would steal output."""
    from building import (
        BuildingArmouredConveyor,
        BuildingBridge,
        BuildingConveyor,
        BuildingSplitter,
    )

    w = state.w
    for dx, dy in DIR4_DELTA:
        nx, ny = ox + dx, oy + dy
        if not state.in_bounds(nx, ny):
            continue
        ni = ny * w + nx
        bld = state.building[ni]
        if bld is None:
            continue
        if bld.team == state.my_team:
            continue
        if isinstance(
            bld,
            (
                BuildingConveyor,
                BuildingArmouredConveyor,
                BuildingSplitter,
                BuildingBridge,
            ),
        ):
            return False
    return True


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
    _t = ct.get_cpu_time_elapsed
    _t0 = _t()
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

        from building import (
            BuildingArmouredConveyor,
            BuildingConveyor,
            BuildingSplitter,
        )

        for ddx, ddy in DIR4_DELTA:
            nx, ny = hx + ddx, hy + ddy
            if not state.in_bounds(nx, ny):
                continue
            ni = ny * w + nx
            bld = state.building[ni]
            match bld:
                case (
                    BuildingConveyor(team=team)
                    | BuildingArmouredConveyor(team=team)
                    | BuildingSplitter(team=team)
                ) if team == state.my_team:
                    conv_dir = (ddx, ddy)
                case BuildingGunner(team=team) if team == state.my_team:
                    has_gunner = True
                case BuildingBarrier(team=team) if team == state.my_team:
                    pass

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
        from building import (
            BuildingArmouredConveyor,
            BuildingConveyor,
            BuildingSplitter,
        )

        needs_splitter = (
            isinstance(cbld, (BuildingConveyor, BuildingArmouredConveyor))
            and cbld.team == state.my_team
        )
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
                    if (
                        isinstance(state.building[si], BuildingSentinel)
                        and state.building[si].team == state.my_team
                    ):
                        has_sentinel = True

        if is_splitter and not has_sentinel:
            sdx, sdy = cbld.direction.delta()
            for odx, ody in [(-sdy, sdx), (sdy, -sdx)]:
                sx, sy = cx + odx, cy + ody
                if not state.in_bounds(sx, sy):
                    continue
                si = sy * w + sx
                env = state.env[si]
                if env in (
                    Environment.WALL,
                    Environment.ORE_TITANIUM,
                    Environment.ORE_AXIONITE,
                ):
                    continue
                sbld = state.building[si]
                if sbld is not None and not isinstance(
                    sbld, (BuildingRoad, BuildingMarker)
                ):
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

    # Immediate: already adjacent to ore -> road around it first, then place

    _t1 = _t()
    for ddx, ddy in DIR4_DELTA:
        ni = (pos.y + ddy) * w + (pos.x + ddx)
        if ni in unharvested:
            ore_pos = Position(pos.x + ddx, pos.y + ddy)
            if ore_pos in state.unit_tiles:
                continue
            if not _adjacent_safe_for_harvester(state, ore_pos.x, ore_pos.y):
                continue
            bid = ct.get_tile_building_id(ore_pos)
            h_cost, _ = ct.get_harvester_cost()
            ti, _ = ct.get_global_resources()
            if ti < h_cost:
                return Direction.CENTRE, None  # Wait for Ti
            # Destroy any friendly building on the ore tile
            if bid is not None:
                if ct.get_team(bid) == state.my_team and ct.can_destroy(ore_pos):
                    ct.destroy(ore_pos)
                elif ct.get_team(bid) != state.my_team:
                    continue
            if ct.can_build_harvester(ore_pos):
                return Direction.CENTRE, PlaceHarvester(ore_pos)
            state.blocked_ore[ni] = state.age + state.birthday

    # Pick best ore and walk toward it
    _t2 = _t()
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
    import sys

    print(
        f"HARV: pos=({pos.x},{pos.y}) ore={len(unharvested)} scored={len(scored)} blocked={len(state.blocked_ore)}",
        file=sys.stderr,
    )

    for _, oi in scored:
        bld = state.building[oi]
        # Check blocked ore — unblock if we can see it's free now
        ore_p = Position(oi % w, oi // w)
        if oi in state.blocked_ore:
            rnd = state.age + state.birthday
            blocked_at = state.blocked_ore[oi]
            if rnd - blocked_at > 100:
                state.blocked_ore.pop(oi, None)
            elif state.last_seen[oi] == rnd:
                if bld is None and ore_p not in state.unit_tiles:
                    state.blocked_ore.pop(oi, None)
                else:
                    continue
            else:
                continue
        # Skip if ore has a building we can't remove
        if bld is not None:
            from building import (
                BuildingBarrier,
                BuildingHarvester,
                BuildingMarker,
                BuildingRoad,
            )

            if isinstance(bld, BuildingBarrier) and bld.team == state.my_team:
                pass  # our barrier — we'll destroy it when placing harvester
            elif not isinstance(bld, (BuildingRoad, BuildingMarker, BuildingHarvester)):
                state.blocked_ore[oi] = state.age + state.birthday
                continue
        # Skip if enemy unit is standing on the ore
        if ore_p in state.unit_tiles:
            state.blocked_ore[oi] = state.age + state.birthday
            continue
        if is_claimed(state, oi, TaskKind.NAV_ORE):
            print(f"HARV:   ({oi % w},{oi // w}) claimed", file=sys.stderr)
            continue
        ore_pos = Position(oi % w, oi // w)
        adj = cardinal_adjacent(state, pos, ore_pos)
        if adj is None:
            print(f"HARV:   ({oi % w},{oi // w}) no adj", file=sys.stderr)
            continue
        result = move_toward_with_road(state, ct, adj)
        if result is None:
            print(
                f"HARV:   ({oi % w},{oi // w}) no path to ({adj.x},{adj.y})",
                file=sys.stderr,
            )
            continue
        move, build = result
        if move == Direction.CENTRE and build is None:
            print(
                f"HARV:   ({oi % w},{oi // w}) stuck at ({adj.x},{adj.y})",
                file=sys.stderr,
            )
            continue
        # If we'll be adjacent after moving, DON'T fast-place — let the
        # immediate check handle it next turn (with barrier + road sequence)

        print(
            f"HARV: id={ct.get_id()} ({pos.x},{pos.y}) -> ore ({oi % w},{oi // w}) adj ({adj.x},{adj.y}) {move.name}",
            file=sys.stderr,
        )
        state.claim = MarkerTaskClaim(TaskKind.NAV_ORE, oi, rnd)
        return move, build

    return None
