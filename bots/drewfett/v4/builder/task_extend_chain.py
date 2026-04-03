"""Extend conveyor chain from network toward a meeting point.

Reads MarkerChainPlan markers to find meeting points where another
builder plans to connect a harvester. Builds conveyors from our
existing Ti network toward the meeting point, so the two chains
meet in the middle and connect faster.

Builds from the meeting point side first (like FEED_TURRET) so
partially-built chains have no flow and connect_excess won't
interfere.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Controller, Direction, Position
from flow_astar import FlowAstar
from util import INF

from .helpers import move_toward_with_road
from .task_connect_excess import SearchKind, _already_connected, _build_action

if TYPE_CHECKING:
    from .action import Action
    from .state import State


def _find_best_plan(state: State) -> int | None:
    """Find the nearest unconnected meeting point."""
    if not state.chain_plans:
        return None
    w = state.w
    pos = state.pos
    f = state.flow
    best: int | None = None
    best_dist = INF

    for ti in state.chain_plans:
        # Skip if already has flow (chain already connected)
        if f.ti[ti] > 0:
            continue
        tx, ty = ti % w, ti // w
        dist = (pos.x - tx) ** 2 + (pos.y - ty) ** 2
        if dist < best_dist:
            best_dist = dist
            best = ti

    return best


def _find_nearest_network(state: State, target_idx: int) -> tuple[int, int] | None:
    """Find nearest Ti-flowing network tile to the meeting point."""
    w = state.w
    f = state.flow
    tx, ty = target_idx % w, target_idx // w
    best: tuple[int, int] | None = None
    best_dist = INF

    for i in state.my_transport | state.my_harvesters:
        if f.ti[i] < 0.01 and i not in state.my_harvesters:
            continue
        ix, iy = i % w, i // w
        dist = (tx - ix) ** 2 + (ty - iy) ** 2
        if dist < best_dist:
            best_dist = dist
            best = (ix, iy)

    return best


def extend_chain(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    target_idx = _find_best_plan(state)
    if target_idx is None:
        return None

    w = state.w
    tx, ty = target_idx % w, target_idx // w

    network = _find_nearest_network(state, target_idx)
    if network is None:
        return None

    nx, ny = network
    ni = ny * w + nx

    # If network tile IS the meeting point, nothing to build
    if ni == target_idx:
        return None

    # FlowAstar from network tile toward meeting point
    search = FlowAstar(state, nx, ny, {target_idx}, 0, hx=tx, hy=ty)
    path = search.compute(lambda: ct.get_cpu_time_elapsed() < 1000)
    if path is None or len(path) < 2:
        return None

    # Build from meeting point side first (reverse order)
    pos = state.pos
    for k in range(len(path) - 1, 0, -1):
        x, y = path[k] % w, path[k] // w
        px, py = path[k - 1] % w, path[k - 1] // w

        if _already_connected(state, path[k - 1], px, py, x, y, SearchKind.MIXED):
            continue

        build_at = Position(px, py)
        action = _build_action(build_at, x, y, SearchKind.MIXED)

        if pos.distance_squared(build_at) <= 2:
            return Direction.CENTRE, action
        return move_toward_with_road(state, ct, build_at)

    return None
