from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import EntityType
from marker import Marker, MarkerSymmetry
from util.debug import debug as log

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


def update_markers(self: Builder, ct: Controller) -> None:
    """Read visible friendly markers and integrate into state. Currently
    just handles MarkerSymmetry: seeing one collapses this builder's
    symmetry hypotheses to the marker's value."""
    if self.symmetry is not None:
        return
    for pos in self.nearby_tiles:
        bid = ct.get_tile_building_id(pos)
        if bid is None:
            continue
        if ct.get_entity_type(bid) != EntityType.MARKER:
            continue
        if ct.get_team(bid) != self.my_team:
            continue
        m = Marker.decode(ct.get_marker_value(bid))
        if isinstance(m, MarkerSymmetry):
            self.symmetry = m.symmetry
            self.symmetry_candidates = {m.symmetry}
            log(
                f"update_markers: symmetry resolved to {m.symmetry} via "
                f"marker at {pos}",
            )
            return
