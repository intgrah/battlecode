"""Road tiles adjacent to our harvesters so builders can access them."""

from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingRoad,
    BuildingSplitter,
)
from cambc import Controller, Direction, Environment, Position
from util import DIR4_DELTA

from .action import Action, PlaceRoad
from .helpers import move_toward_with_road

if TYPE_CHECKING:
    from .state import State

_WALKABLE = (BuildingRoad, BuildingConveyor, BuildingArmouredConveyor, BuildingSplitter, BuildingBridge)


def road_harvesters(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    """Find unroaded tiles adjacent to our harvesters and road them."""
    pos = state.pos
    w = state.w

    for hi in state.my_harvesters:
        hx, hy = hi % w, hi // w
        for rdx, rdy in DIR4_DELTA:
            rx, ry = hx + rdx, hy + rdy
            if not state.in_bounds(rx, ry):
                continue
            ri = ry * w + rx
            env = state.env[ri]
            if env in (Environment.WALL, Environment.ORE_TITANIUM, Environment.ORE_AXIONITE):
                continue
            bld = state.building[ri]
            if isinstance(bld, _WALKABLE):
                continue
            # Needs a road
            rp = Position(rx, ry)
            if pos.distance_squared(rp) <= 2 and ct.can_build_road(rp):
                return Direction.CENTRE, PlaceRoad(rp)
            return move_toward_with_road(state, ct, rp)

    return None
