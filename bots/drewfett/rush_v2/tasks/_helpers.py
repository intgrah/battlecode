"""Shared helpers for builder tasks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from action import PlaceRoad
from cambc import Position
from nav import find_path
from turn import ActionMove, MoveOnly, Turn
from util import COST_IMPASSABLE, DIR4_DELTA, INF

if TYPE_CHECKING:
    from cambc import Controller
    from state import State


def move_toward(state: State, ct: Controller, target: Position) -> Turn | None:
    """Move toward target, building a road if needed."""
    path = find_path(state, target.x, target.y)
    if path is None or len(path) < 2:
        return None
    w = state.w
    nx, ny = path[1] % w, path[1] // w
    nxt = Position(nx, ny)
    d = state.pos.direction_to(nxt)
    if ct.can_move(d):
        return MoveOnly(d)
    # Can't move -- try building a road first
    if ct.can_build_road(nxt):
        return ActionMove(PlaceRoad(nxt), d)
    return None


def chebyshev(ax: int, ay: int, bx: int, by: int) -> int:
    """Chebyshev (king-move) distance."""
    return max(abs(ax - bx), abs(ay - by))


def cardinal_adjacent_free(
    state: State, pos: Position, target: Position
) -> Position | None:
    """Find the closest free cardinal neighbour of *target* for the builder to stand on."""
    best: Position | None = None
    best_dist = INF
    w = state.w
    for ddx, ddy in DIR4_DELTA:
        ax, ay = target.x + ddx, target.y + ddy
        if not state.in_bounds(ax, ay):
            continue
        if state.cost[ay * w + ax] >= COST_IMPASSABLE:
            continue
        if Position(ax, ay) in state.unit_tiles:
            continue
        dist = chebyshev(pos.x, pos.y, ax, ay)
        if dist < best_dist:
            best_dist = dist
            best = Position(ax, ay)
    return best


def is_claimed(state: State, tile_index: int, kind: int) -> bool:
    """Check whether another builder has already claimed this tile."""
    for c in state.claims:
        if c.tile_index == tile_index and c.kind == kind:
            # Don't count our own previous claim as blocking
            if (
                state.last_claim is not None
                and c.tile_index == state.last_claim.tile_index
                and c.kind == state.last_claim.kind
            ):
                continue
            return True
    return False
