"""Spend excess Ti on defensive sentinels near our harvesters.

Only runs when Ti is high and we have harvesters worth protecting.
Places sentinels on free tiles adjacent to our harvesters, facing
away from the harvester (toward likely enemy approach).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from building import BuildingMarker, BuildingRoad, BuildingSentinel
from cambc import Controller, Direction, Position
from util import DIR4_DELTA

from .action import Action, PlaceSentinel
from .helpers import move_toward_with_road, step_off_and_build

if TYPE_CHECKING:
    from .state import State

_TI_THRESHOLD = 500  # don't fortify unless we have this much Ti


def fortify(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    """Place a sentinel near an unprotected harvester."""
    ti, _ = ct.get_global_resources()
    if ti < _TI_THRESHOLD:
        return None

    s_cost, _ = ct.get_sentinel_cost()
    if ti < s_cost:
        return None

    w = state.w
    pos = state.pos
    my_team = state.my_team

    # Find harvesters without a nearby friendly sentinel
    for hi in state.my_harvesters:
        hx, hy = hi % w, hi // w

        # Check if already protected (friendly sentinel within d²≤8)
        protected = False
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                nx, ny = hx + dx, hy + dy
                if not state.in_bounds(nx, ny):
                    continue
                ni = ny * w + nx
                bld = state.building[ni]
                if isinstance(bld, BuildingSentinel) and bld.team == my_team:
                    protected = True
                    break
            if protected:
                break
        if protected:
            continue

        # Find best placement tile adjacent to harvester
        best_pos: tuple[int, int] | None = None
        best_dist = 1_000_000
        for dx, dy in DIR4_DELTA:
            nx, ny = hx + dx, hy + dy
            if not state.in_bounds(nx, ny):
                continue
            ni = ny * w + nx
            nbld = state.building[ni]
            if nbld is not None and not isinstance(nbld, (BuildingRoad, BuildingMarker)):
                continue
            # Prefer tile closest to builder
            dist = (pos.x - nx) ** 2 + (pos.y - ny) ** 2
            if dist < best_dist:
                best_dist = dist
                best_pos = (nx, ny)

        if best_pos is None:
            continue

        sx, sy = best_pos
        sentinel_pos = Position(sx, sy)
        # Face away from harvester (toward enemy approach)
        facing = sentinel_pos.direction_to(Position(hx, hy)).opposite()
        if facing == Direction.CENTRE:
            facing = Direction.NORTH

        if pos == sentinel_pos:
            return step_off_and_build(ct, PlaceSentinel(sentinel_pos, facing))
        if pos.distance_squared(sentinel_pos) <= 2:
            nbld = state.building[sy * w + sx]
            if nbld is not None and nbld.team == my_team and ct.can_destroy(sentinel_pos):
                ct.destroy(sentinel_pos)
            if ct.can_build_sentinel(sentinel_pos, facing):
                return Direction.CENTRE, PlaceSentinel(sentinel_pos, facing)
        return move_toward_with_road(state, ct, sentinel_pos)

    return None
