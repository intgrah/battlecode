"""Shared helpers for builder tasks.

Key functions:
- move_toward_with_road: BFS-based navigation with road paving
- cardinal_adjacent: deterministic adjacent tile picker
- step_off_and_build: step off current tile to place impassable building
- execute: execute an action with cost checks
- is_claimed: check marker claims
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from action import (
    Action,
    Fire,
    Heal,
    PlaceBarrier,
    PlaceBridge,
    PlaceConveyor,
    PlaceFoundry,
    PlaceGunner,
    PlaceHarvester,
    PlaceLauncher,
    PlaceRoad,
    PlaceSentinel,
    PlaceSplitter,
    SelfDestruct,
)
from cambc import Controller, Direction, EntityType, Position
from marker import TaskKind
from util import COST_IMPASSABLE, DIR4_DELTA, DIR8, INF

if TYPE_CHECKING:
    from .state import State

# BFS weight indices map to these directions.
# NavBfs.step() returns (NE, SE, SW, NW, N, E, S, W).
_BFS_DIRECTIONS: tuple[Direction, ...] = (
    Direction.NORTHEAST,
    Direction.SOUTHEAST,
    Direction.SOUTHWEST,
    Direction.NORTHWEST,
    Direction.NORTH,
    Direction.EAST,
    Direction.SOUTH,
    Direction.WEST,
)
_DELTAS: tuple[tuple[int, int], ...] = (
    (1, -1),
    (1, 1),
    (-1, 1),
    (-1, -1),
    (0, -1),
    (1, 0),
    (0, 1),
    (-1, 0),
)
_IS_DIAG: tuple[int, ...] = (1, 1, 1, 1, 0, 0, 0, 0)


def move_toward_with_road(
    state: State,
    ct: Controller,
    target: Position,
) -> tuple[Direction, Action | None]:
    """Navigate toward target using BFS weights, paving roads if needed."""
    pos = state.pos
    if pos == target:
        return Direction.CENTRE, None

    nav = state.nav_bfs
    if nav is None:
        return Direction.CENTRE, None

    nav.set_goal(target)
    weights = nav.step(pos, max_iters=512)

    if weights == (0, 0, 0, 0, 0, 0, 0, 0):
        return Direction.CENTRE, None

    # Sort by weight. Break ties: prefer cardinal over diagonal, then
    # by Euclidean distance to target.
    tx, ty = target.x, target.y
    indexed: list[tuple[int, int, int, int]] = []
    for i in range(8):
        w = weights[i]
        if w >= INF:
            continue
        ddx, ddy = _DELTAS[i]
        nx, ny = pos.x + ddx, pos.y + ddy
        dist_sq = (nx - tx) ** 2 + (ny - ty) ** 2
        indexed.append((w, _IS_DIAG[i], dist_sq, i))
    indexed.sort()

    if not indexed:
        return Direction.CENTRE, None

    road_cost, _ = ct.get_road_cost()
    ti_res, _ = ct.get_global_resources()
    map_w = state.w
    danger = state.danger_zones

    # For each direction (best first): try move, then road. Skip danger zones.
    for _w, _d, _ds, i in indexed:
        d = _BFS_DIRECTIONS[i]
        nxt = pos.add(d)
        ni = nxt.y * map_w + nxt.x
        if ni in danger:
            continue
        if ct.can_move(d):
            return d, None
        if ti_res >= road_cost and ct.can_build_road(nxt):
            return d, PlaceRoad(nxt)

    # All directions dangerous -- try without danger check as last resort
    for _w, _d, _ds, i in indexed:
        d = _BFS_DIRECTIONS[i]
        if ct.can_move(d):
            return d, None

    return Direction.CENTRE, None


def cardinal_adjacent(
    state: State, _pos: Position, target: Position
) -> Position | None:
    """Pick a walkable cardinal neighbor of target.

    Deterministic: scores by distance to CORE, not builder position.
    This prevents oscillation when multiple builders compete.
    """
    core = state.my_core
    best: Position | None = None
    best_dist = INF
    for ddx, ddy in DIR4_DELTA:
        ax, ay = target.x + ddx, target.y + ddy
        if not state.in_bounds(ax, ay):
            continue
        if state.walkable(ax, ay) >= COST_IMPASSABLE:
            continue
        # Deterministic: closest to core, not to builder
        dist = (core.x - ax) ** 2 + (core.y - ay) ** 2
        if dist < best_dist:
            best_dist = dist
            best = Position(ax, ay)
    return best


def step_off_and_build(
    ct: Controller,
    build: Action,
) -> tuple[Direction, Action] | None:
    """Step off the current tile so an impassable building can be placed.

    If an adjacent tile is walkable, move there and build in one turn.
    If not, place a road on an adjacent tile -- next turn we can step off.
    """
    pos = ct.get_position()
    for d in DIR8:
        if ct.can_move(d):
            return d, build
    # No walkable neighbor -- pave a road so we can step off next turn
    for d in DIR8:
        adj = pos.add(d)
        if ct.can_build_road(adj):
            return Direction.CENTRE, PlaceRoad(adj)
    return None


def is_claimed(state: State, tile_index: int, kind: TaskKind) -> bool:
    """Check if another builder has claimed this tile for this task kind."""
    if kind == TaskKind.FIX_EXCESS:
        return False
    for c in state.claims:
        if c.tile_index == tile_index and c.kind == kind:
            if (
                state.last_claim is not None
                and c.tile_index == state.last_claim.tile_index
                and c.kind == state.last_claim.kind
            ):
                continue
            return True
    return False


def _destroy_friendly(ct: Controller, pos: Position) -> None:
    """Destroy low-value friendly buildings (roads, markers) to make room."""
    bid = ct.get_tile_building_id(pos)
    if bid is None:
        return
    if ct.get_team(bid) != ct.get_team():
        return
    if ct.get_entity_type(bid) in (
        EntityType.ROAD,
        EntityType.MARKER,
    ) and ct.can_destroy(pos):
        ct.destroy(pos)


def execute(action: Action, ct: Controller) -> None:
    """Execute a build/heal/fire action with cost and capability checks."""
    ti, _ = ct.get_global_resources()
    match action:
        case PlaceHarvester(pos):
            cost, _ = ct.get_harvester_cost()
            if ti >= cost:
                _destroy_friendly(ct, pos)
                if ct.can_build_harvester(pos):
                    ct.build_harvester(pos)
        case PlaceConveyor(pos, direction):
            cost, _ = ct.get_conveyor_cost()
            if ti >= cost:
                _destroy_friendly(ct, pos)
                can = ct.can_build_conveyor(pos, direction)
                if can:
                    ct.build_conveyor(pos, direction)
        case PlaceBridge(pos, target):
            cost, _ = ct.get_bridge_cost()
            if ti >= cost:
                _destroy_friendly(ct, pos)
                if ct.can_build_bridge(pos, target):
                    ct.build_bridge(pos, target)
        case PlaceRoad(pos):
            cost, _ = ct.get_road_cost()
            if ti >= cost and ct.can_build_road(pos):
                ct.build_road(pos)
        case PlaceSplitter(pos, direction):
            cost, _ = ct.get_splitter_cost()
            if ti >= cost:
                _destroy_friendly(ct, pos)
                if ct.can_build_splitter(pos, direction):
                    ct.build_splitter(pos, direction)
        case PlaceBarrier(pos):
            cost, _ = ct.get_barrier_cost()
            if ti >= cost:
                _destroy_friendly(ct, pos)
                if ct.can_build_barrier(pos):
                    ct.build_barrier(pos)
        case PlaceSentinel(pos, direction):
            cost, _ = ct.get_sentinel_cost()
            if ti >= cost:
                _destroy_friendly(ct, pos)
                if ct.can_build_sentinel(pos, direction):
                    ct.build_sentinel(pos, direction)
        case PlaceGunner(pos, direction):
            cost, _ = ct.get_gunner_cost()
            if ti >= cost:
                _destroy_friendly(ct, pos)
                if ct.can_build_gunner(pos, direction):
                    ct.build_gunner(pos, direction)
        case PlaceLauncher(pos):
            cost, _ = ct.get_launcher_cost()
            if ti >= cost:
                _destroy_friendly(ct, pos)
                if ct.can_build_launcher(pos):
                    ct.build_launcher(pos)
        case PlaceFoundry(pos):
            cost, _ = ct.get_foundry_cost()
            if ti >= cost:
                _destroy_friendly(ct, pos)
                if ct.can_build_foundry(pos):
                    ct.build_foundry(pos)
        case Heal(pos):
            if ct.can_heal(pos):
                ct.heal(pos)
        case SelfDestruct():
            ct.self_destruct()
        case Fire():
            pos = ct.get_position()
            if ct.can_fire(pos):
                ct.fire(pos)
