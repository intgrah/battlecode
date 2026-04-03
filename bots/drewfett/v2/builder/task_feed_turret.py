"""Feed unfed friendly turrets from Ti sources.

Finds the nearest Ti source (harvester output, splitter side, conveyor
output, or conveyor-to-convert), then uses FlowAstar to route from the
source tap point to the turret tile itself. The turret's facing tile is
blocked so FlowAstar only approaches from valid input directions.

Builds the chain from the turret side first so partially-built chains
have no Ti flow and connect_excess won't interfere.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingConveyor,
    BuildingGunner,
    BuildingMarker,
    BuildingRoad,
    BuildingSentinel,
    BuildingSplitter,
)
from cambc import Controller, Direction, Environment, Position
from flow_astar import FlowAstar
from util import DIR4_DELTA, INF

from .action import Action, PlaceSplitter
from .helpers import move_toward_with_road, valid_splitter_orientations
from .task_connect_excess import SearchKind, _already_connected, _build_action

if TYPE_CHECKING:
    from .state import State

_MAX_SEARCH_DIST_SQ = 100
_CONVERT_PENALTY = 20


def _find_unfed_turret(state: State) -> int | None:
    w = state.w
    f = state.flow
    pos = state.pos
    best: int | None = None
    best_dist = INF

    for ti in state.my_turrets:
        bld = state.building[ti]
        match bld:
            case BuildingSentinel() | BuildingGunner():
                pass
            case _:
                continue
        if f.ti[ti] > 0:
            continue
        tx, ty = ti % w, ti // w
        dist = (pos.x - tx) ** 2 + (pos.y - ty) ** 2
        if dist < best_dist:
            best_dist = dist
            best = ti

    return best


def _valid_tap(state: State, ni: int) -> bool:
    """Check if a tile can serve as a tap point for a new conveyor chain."""
    env = state.env[ni]
    if env in (Environment.WALL, Environment.ORE_TITANIUM, Environment.ORE_AXIONITE):
        return False
    bld = state.building[ni]
    match bld:
        case None:
            return True
        case BuildingRoad(team=team) | BuildingMarker(team=team):
            return team == state.my_team
        case _:
            return False


def _find_ammo_source(
    state: State,
    turret_idx: int,
) -> tuple[str, int, Direction | None, int, int] | None:
    """Find best Ti source to tap for feeding a turret.

    Returns (kind, source_idx, splitter_dir, start_x, start_y) or None.
    """
    w = state.w
    f = state.flow
    tx, ty = turret_idx % w, turret_idx // w

    best: tuple[str, int, Direction | None, int, int] | None = None
    best_cost = INF

    # Tier 1: Harvesters with free output
    for hi in state.my_harvesters | state.en_harvesters:
        if hi in state.en_harvesters and state.env[hi] != Environment.ORE_TITANIUM:
            continue
        hx, hy = hi % w, hi // w
        for dx, dy in DIR4_DELTA:
            nx, ny = hx + dx, hy + dy
            if not state.in_bounds(nx, ny):
                continue
            ni = ny * w + nx
            if not _valid_tap(state, ni):
                continue
            cost = (nx - tx) ** 2 + (ny - ty) ** 2
            if cost < best_cost:
                best_cost = cost
                best = ("harvester", hi, None, nx, ny)

    # Tier 2: Existing splitters with free side output
    for ci in state.my_transport:
        bld = state.building[ci]
        match bld:
            case BuildingSplitter(direction=d, team=team) if team == state.my_team:
                pass
            case _:
                continue
        if f.ti[ci] < 0.01:
            continue
        cx, cy = ci % w, ci // w
        if (cx - tx) ** 2 + (cy - ty) ** 2 > _MAX_SEARCH_DIST_SQ:
            continue
        sdx, sdy = d.delta()
        for odx, ody in [(-sdy, sdx), (sdy, -sdx)]:
            side_x, side_y = cx + odx, cy + ody
            if not state.in_bounds(side_x, side_y):
                continue
            si = side_y * w + side_x
            if not _valid_tap(state, si):
                continue
            cost = (side_x - tx) ** 2 + (side_y - ty) ** 2
            if cost < best_cost:
                best_cost = cost
                best = ("splitter", ci, d, side_x, side_y)

    # Tier 2b: Conveyors with free output (no conversion needed)
    for ci in state.my_transport:
        bld = state.building[ci]
        match bld:
            case BuildingConveyor(direction=d, team=team) if team == state.my_team:
                pass
            case _:
                continue
        if f.ti[ci] < 0.01:
            continue
        cx, cy = ci % w, ci // w
        if (cx - tx) ** 2 + (cy - ty) ** 2 > _MAX_SEARCH_DIST_SQ:
            continue
        ddx, ddy = d.delta()
        ox, oy = cx + ddx, cy + ddy
        if not state.in_bounds(ox, oy):
            continue
        oi = oy * w + ox
        if not _valid_tap(state, oi):
            continue
        cost = (ox - tx) ** 2 + (oy - ty) ** 2
        if cost < best_cost:
            best_cost = cost
            best = ("output", ci, None, ox, oy)

    # Tier 3: Conveyors to convert (penalized)
    for ci in state.my_transport:
        bld = state.building[ci]
        match bld:
            case BuildingConveyor(direction=d, team=team) if team == state.my_team:
                pass
            case _:
                continue
        if f.ti[ci] < 0.01:
            continue
        cx, cy = ci % w, ci // w
        if (cx - tx) ** 2 + (cy - ty) ** 2 > _MAX_SEARCH_DIST_SQ:
            continue
        for sdir in valid_splitter_orientations(state, ci, f.ti[ci]):
            sdx, sdy = sdir.delta()
            for odx, ody in [(-sdy, sdx), (sdy, -sdx)]:
                side_x, side_y = cx + odx, cy + ody
                if not state.in_bounds(side_x, side_y):
                    continue
                si = side_y * w + side_x
                if not _valid_tap(state, si):
                    continue
                cost = (side_x - tx) ** 2 + (side_y - ty) ** 2 + _CONVERT_PENALTY
                if cost < best_cost:
                    best_cost = cost
                    best = ("convert", ci, sdir, side_x, side_y)

    return best


def feed_turret(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    turret_idx = _find_unfed_turret(state)
    if turret_idx is None:
        return None

    w = state.w
    tx, ty = turret_idx % w, turret_idx // w

    source = _find_ammo_source(state, turret_idx)
    if source is None:
        return None

    kind, src_idx, splitter_dir, start_x, start_y = source
    pos = state.pos

    # If "convert", first convert the conveyor to a splitter
    if kind == "convert":
        bld = state.building[src_idx]
        if isinstance(bld, BuildingConveyor):
            sp_cost, _ = ct.get_splitter_cost()
            ti, _ = ct.get_global_resources()
            if ti < sp_cost:
                return None
            conv_pos = Position(src_idx % w, src_idx // w)
            if pos.distance_squared(conv_pos) <= 2:
                assert splitter_dir is not None
                return Direction.CENTRE, PlaceSplitter(conv_pos, splitter_dir)
            return move_toward_with_road(state, ct, conv_pos)
        # Already converted — fall through to chain routing

    # Block the turret's facing tile so FlowAstar won't route through it
    facing_idx = -1
    bld = state.building[turret_idx]
    match bld:
        case BuildingSentinel(direction=facing) | BuildingGunner(direction=facing):
            fdx, fdy = facing.delta()
            fx, fy = tx + fdx, ty + fdy
            if state.in_bounds(fx, fy):
                facing_idx = fy * w + fx

    old_blocked = False
    if facing_idx >= 0:
        old_blocked = state.flow.blocked[facing_idx]
        state.flow.blocked[facing_idx] = True

    # FlowAstar from source tap to turret tile
    search = FlowAstar(state, start_x, start_y, {turret_idx}, 0, hx=tx, hy=ty)
    path = search.compute(lambda: ct.get_cpu_time_elapsed() < 1000)

    # Restore blocked state
    if facing_idx >= 0:
        state.flow.blocked[facing_idx] = old_blocked

    if path is not None and len(path) >= 2:
        return _walk_chain(state, ct, path)

    return None


def _walk_chain(
    state: State,
    ct: Controller,
    path: list[int],
) -> tuple[Direction, Action | None] | None:
    """Build chain from turret side first.

    path[-1] is the turret tile (already built). Build conveyors at
    path[0:-1] in reverse order so partially-built chains have no Ti
    flow and connect_excess won't interfere.
    """
    w = state.w
    pos = state.pos

    for k in range(len(path) - 2, -1, -1):
        x, y = path[k] % w, path[k] // w
        nx, ny = path[k + 1] % w, path[k + 1] // w

        if _already_connected(state, path[k], x, y, nx, ny, SearchKind.MIXED):
            continue

        build_at = Position(x, y)
        action = _build_action(build_at, nx, ny, SearchKind.MIXED)

        if pos.distance_squared(build_at) <= 2:
            return Direction.CENTRE, action
        return move_toward_with_road(state, ct, build_at)

    return None
