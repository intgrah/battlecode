"""Translation of `bots/intgrah/v54.7.9/breach/__init__.py`."""

from __future__ import annotations

from unit import in_bounds
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Controller
from unit import UnitState


class Breach:
    state: UnitState

    def __init__(self):
        self.state = UnitState()

    def unit_state(self):
        return self.state

    def unit_state_mut(self):
        return self.state

    def run(self, ct):
        self.state.cache_per_turn_state(ct)
        self.state.check_symmetry_marker(ct)
        raise NotImplementedError("Breach behaviour not implemented")

    def post_init(self, ct):
        """
        ct-dependent init. Runs once on first turn for this unit. Mirrors
        Python `Unit.post_init`.
        """
        s = self.unit_state_mut()
        s.init_static_state(ct)
        s.narrow_symmetry_from_vision(ct)

    def idx(self, pos):
        """
        Position to flat index. Stride is `MAX_WIDTH=50` regardless of actual
        map size.
        """
        return int(pos.y) * 50 + int(pos.x)

    def in_bounds(self, pos):
        """Is in bounds of the actual map."""
        s = self.unit_state()
        return in_bounds(pos, s.width, s.height)
