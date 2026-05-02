"""Translation of `bots/intgrah/v54.7.9/builder/hooks/propagate_symmetry.py`."""
from __future__ import annotations

from cambc import Environment
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cambc import Controller, ControllerApi
if TYPE_CHECKING:
    from builder import Builder
from marker import Marker, MarkerSymmetry
from util.constants import MAX_WIDTH
from util.directions import DIR8

def end_of_turn_propagate_symmetry(builder, ct):
    """
    If we've collapsed to a single symmetry, drop a marker on a
    nearby tile with no existing building so other units that see it
    converge too. Markers are the lowest-priority building — we'd never
    destroy anything to place one, so we only place on tiles that are
    already unbuilt.
    """
    symmetry = builder.symmetry
    if symmetry is None:
        return
    payload = MarkerSymmetry(symmetry=symmetry).encode()
    for d in DIR8:
        target = builder.state.my_pos.add(d)
        if not builder.in_bounds(target):
            continue
        i = int(target.y) * 50 + int(target.x)
        if builder.env[i] == Environment.WALL:
            continue
        if (builder.building_kind[i] is not None):
            continue
        if ct.can_place_marker(target):
            ct.place_marker(target, payload)
            return
