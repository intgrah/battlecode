"""Barrier exposed harvester sides to prevent resource leaking/theft.

Finds harvesters with empty cardinal tiles (no building, not wall/ore)
and places barriers to seal them. Harvester output only goes through
the connected conveyor, not leaking to empty tiles.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Controller, Direction, Environment, Position
from util import DIR4_DELTA

from .action import Action, PlaceBarrier
from .helpers import move_toward_with_road

if TYPE_CHECKING:
    from .state import State


def fortify(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    """Place barriers around exposed harvester sides."""
    b_cost, _ = ct.get_barrier_cost()
    ti, _ = ct.get_global_resources()
    if ti < b_cost:
        return None

    w = state.w
    pos = state.pos

    # Find most-exposed harvester first
    best_target: Position | None = None
    best_exposed = 0
    best_dist = 1_000_000

    for hi in state.my_harvesters:
        hx, hy = hi % w, hi // w
        exposed: list[tuple[int, int]] = []
        for dx, dy in DIR4_DELTA:
            nx, ny = hx + dx, hy + dy
            if not state.in_bounds(nx, ny):
                continue
            ni = ny * w + nx
            if state.building[ni] is not None:
                continue
            env = state.env[ni]
            if env in (
                Environment.WALL,
                Environment.ORE_TITANIUM,
                Environment.ORE_AXIONITE,
            ):
                continue
            exposed.append((nx, ny))

        if not exposed:
            continue

        # Prioritise most exposed, then closest
        for nx, ny in exposed:
            dist = (pos.x - nx) ** 2 + (pos.y - ny) ** 2
            if len(exposed) > best_exposed or (
                len(exposed) == best_exposed and dist < best_dist
            ):
                best_exposed = len(exposed)
                best_dist = dist
                best_target = Position(nx, ny)

    if best_target is None:
        return None

    if pos.distance_squared(best_target) <= 2:
        if ct.can_build_barrier(best_target):
            return Direction.CENTRE, PlaceBarrier(best_target)

    return move_toward_with_road(state, ct, best_target)
