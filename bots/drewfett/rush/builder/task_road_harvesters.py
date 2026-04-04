"""Road tiles adjacent to our harvesters (or ore about to be harvested)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingMarker,
    BuildingRoad,
    BuildingSplitter,
)
from cambc import Controller, Direction, Environment, Position
from util import DIR4_DELTA

from .action import Action, Fire, PlaceRoad
from .helpers import move_toward_with_road

if TYPE_CHECKING:
    from .state import State

_WALKABLE = (
    BuildingRoad,
    BuildingConveyor,
    BuildingArmouredConveyor,
    BuildingSplitter,
    BuildingBridge,
)


def road_around(
    state: State,
    ct: Controller,
    tx: int,
    ty: int,
) -> tuple[Direction, Action | None] | None:
    """Road unroaded cardinal tiles around (tx, ty). Returns action or None if all done."""
    pos = state.pos
    w = state.w
    my_team = state.my_team
    for rdx, rdy in DIR4_DELTA:
        rx, ry = tx + rdx, ty + rdy
        if not state.in_bounds(rx, ry):
            continue
        ri = ry * w + rx
        env = state.env[ri]
        if env == Environment.WALL:
            continue
        bld = state.building[ri]
        # Already walkable with our building — controlled
        if isinstance(bld, _WALKABLE) and bld.team == my_team:
            continue
        # Enemy road — need to walk onto it and fire to destroy
        if isinstance(bld, BuildingRoad) and bld.team != my_team:
            rp = Position(rx, ry)
            if pos == rp:
                return Direction.CENTRE, Fire()
            if pos.distance_squared(rp) <= 2:
                d = pos.direction_to(rp)
                if ct.can_move(d):
                    return d, None  # walk onto it to fire next turn
            return move_toward_with_road(state, ct, rp)
        # Our marker or empty (including ore tiles) — road it
        if bld is None or isinstance(bld, BuildingMarker):
            rp = Position(rx, ry)
            if pos.distance_squared(rp) <= 2:
                can = ct.can_build_road(rp)
                # debug: print(f"ROAD: ...")
                if can:
                    return Direction.CENTRE, PlaceRoad(rp)
            return move_toward_with_road(state, ct, rp)
        # Enemy building we can't easily clear — skip this tile
        continue
    return None


def road_harvesters(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    """Road tiles adjacent to all our harvesters."""
    _t0 = ct.get_cpu_time_elapsed()
    w = state.w
    for hi in state.my_harvesters:
        result = road_around(state, ct, hi % w, hi // w)
        if result is not None:
            return result
    return None
