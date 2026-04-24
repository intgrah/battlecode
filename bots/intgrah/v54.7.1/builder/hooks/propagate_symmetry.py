from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Environment
from marker import MarkerSymmetry
from util.constants import MAX_WIDTH
from util.directions import DIR8

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


def end_of_turn_propagate_symmetry(self: Builder, ct: Controller) -> None:
    """If we've collapsed to a single symmetry, drop a marker on a
    nearby tile with no existing building so other units that see it
    converge too. Markers are the lowest-priority building — we'd never
    destroy anything to place one, so we only place on tiles that are
    already unbuilt."""
    if self.symmetry is None:
        return
    payload = MarkerSymmetry(symmetry=self.symmetry).encode()
    for d in DIR8:
        target = self.my_pos.add(d)
        if not self.in_bounds(target):
            continue
        i = target.y * MAX_WIDTH + target.x
        if self.env[i] == Environment.WALL:
            continue
        if self.buildings[i] is not None:
            continue
        if ct.can_place_marker(target):
            ct.place_marker(target, payload)
            return
