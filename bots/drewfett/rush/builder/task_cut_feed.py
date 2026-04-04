"""Destroy our transport/harvesters that feed enemy turrets.

Scans our transport and harvesters for tiles adjacent to enemy turrets.
If our building is feeding ammo to an enemy gunner/sentinel/breach,
walk there and destroy it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingBreach,
    BuildingGunner,
    BuildingSentinel,
)
from cambc import Controller, Direction, Position
from util import DIR4_DELTA

from .helpers import move_toward_with_road

if TYPE_CHECKING:
    from .action import Action
    from .state import State


def cut_feed(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    w = state.w
    pos = state.pos

    # Check our transport + harvesters for ones adjacent to enemy turrets
    my_feeders = state.my_transport | state.my_harvesters
    if not my_feeders or not state.en_turrets:
        return None

    best: Position | None = None
    best_dist = 1_000_000

    for fi in my_feeders:
        fx, fy = fi % w, fi // w
        for dx, dy in DIR4_DELTA:
            nx, ny = fx + dx, fy + dy
            if not state.in_bounds(nx, ny):
                continue
            ni = ny * w + nx
            if ni not in state.en_turrets:
                continue
            bld = state.building[ni]
            if not isinstance(bld, (BuildingGunner, BuildingSentinel, BuildingBreach)):
                continue
            # Our building is feeding this enemy turret
            target = Position(fx, fy)
            dist = (pos.x - fx) ** 2 + (pos.y - fy) ** 2
            if dist < best_dist:
                best_dist = dist
                best = target

    if best is None:
        return None

    # Walk to it and destroy
    if pos == best:
        if ct.can_destroy(best):
            ct.destroy(best)
        return Direction.CENTRE, None

    if pos.distance_squared(best) <= 2 and ct.can_destroy(best):
        ct.destroy(best)
        return Direction.CENTRE, None

    return move_toward_with_road(state, ct, best)
