"""ECON: connect excess harvester flow to the core network.

Simplified placeholder — finds the closest tile with excess Ti flow and
builds a conveyor toward the nearest existing transport/core tile.
Full FlowAstar routing will be added when it is ported to rush_v2.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from action import PlaceConveyor
from cambc import Controller, Direction, Position
from marker import ClaimKind, MarkerClaim
from turn import ActionMove, ActionOnly, Turn
from util import DELTA_TO_DIR, INF

from ._helpers import move_toward

if TYPE_CHECKING:
    from state import State


def run(state: State, ct: Controller) -> Turn | None:
    """Walk to excess-flow tile and build a conveyor toward infrastructure."""
    excess_idx = _find_excess_tile(state)
    if excess_idx is None:
        return None

    w = state.w
    pos = state.pos
    rnd = ct.get_current_round()

    # Claim the tile so other builders don't duplicate work
    state.claim = MarkerClaim(ClaimKind.FIX_EXCESS, excess_idx, rnd)

    ex, ey = excess_idx % w, excess_idx // w
    excess_pos = Position(ex, ey)

    # Find the nearest transport/core tile to route toward
    goal_idx = _find_nearest_goal(state, excess_idx)
    if goal_idx is None:
        return None

    gx, gy = goal_idx % w, goal_idx // w

    # If we are adjacent (action radius) to the excess tile, build a conveyor
    if pos.distance_squared(excess_pos) <= 2:
        direction = _conveyor_direction(ex, ey, gx, gy)
        if direction is not None:
            conv_action = PlaceConveyor(excess_pos, direction)
            # Try to step away after building so we don't block the path
            step_dir = pos.direction_to(Position(gx, gy))
            if ct.can_move(step_dir):
                return ActionMove(conv_action, step_dir)
            return ActionOnly(conv_action)

    # Not adjacent — walk toward the excess tile
    return move_toward(state, ct, excess_pos)


def _find_excess_tile(state: State) -> int | None:
    """Find the closest tile with excess Ti flow in our infrastructure."""
    pos = state.pos
    w = state.w
    f = state.flow
    sources = state.my_harvesters | state.my_transport | state.my_foundries

    best_idx: int | None = None
    best_dist: int = INF

    for i in sources:
        if f.ti_excess[i] <= 0.01:
            continue
        ix, iy = i % w, i // w
        dist = max(abs(pos.x - ix), abs(pos.y - iy))
        if dist < best_dist:
            best_dist = dist
            best_idx = i

    return best_idx


def _find_nearest_goal(state: State, excess_idx: int) -> int | None:
    """Find the nearest transport/core tile that could receive more flow."""
    w = state.w
    ex, ey = excess_idx % w, excess_idx // w
    goals = state.my_transport | state.my_core_tiles
    f = state.flow

    best_idx: int | None = None
    best_dist: int = INF

    for i in goals:
        # Skip tiles that are already at capacity (fully blocked)
        if f.blocked[i]:
            continue
        gx, gy = i % w, i // w
        dist = max(abs(ex - gx), abs(ey - gy))
        if dist < best_dist:
            best_dist = dist
            best_idx = i

    return best_idx


def _conveyor_direction(
    ex: int,
    ey: int,
    gx: int,
    gy: int,
) -> Direction | None:
    """Pick a cardinal direction from (ex, ey) toward (gx, gy)."""
    dx = gx - ex
    dy = gy - ey

    # Prefer the axis with the larger delta
    if dx == 0 and dy == 0:
        return None

    candidates: list[tuple[int, int]] = []
    if abs(dx) >= abs(dy):
        candidates.append((_sign(dx), 0))
        if dy != 0:
            candidates.append((0, _sign(dy)))
    else:
        candidates.append((0, _sign(dy)))
        if dx != 0:
            candidates.append((_sign(dx), 0))

    for ddx, ddy in candidates:
        d = DELTA_TO_DIR.get((ddx, ddy))
        if d is not None and d in (
            Direction.NORTH,
            Direction.EAST,
            Direction.SOUTH,
            Direction.WEST,
        ):
            return d

    return None


def _sign(x: int) -> int:
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0
