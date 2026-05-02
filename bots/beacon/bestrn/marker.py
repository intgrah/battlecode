"""
Translation of `bots/intgrah/v54.7.9/marker/__init__.py`.

Python defines an `ABC` `Marker` with auto-registered subclasses (one tag
per class, assigned at class-definition time). Since the only concrete
variant in v54.7.9 is `MarkerSymmetry`, the Rust translation is a single
enum: adding a new variant means adding a new arm here, in declaration
order (matching Python's `_registry` ordering — `MarkerSymmetry` is tag 0).
"""
from __future__ import annotations

from typing import Final
from dataclasses import dataclass

from cambc import EntityType
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cambc import Controller, ControllerApi, Position, Team
from util.symmetry import Symmetry
KEY: Final[int] = 3735928559
"""XOR key applied to the encoded `u32` to scramble the wire format."""
TAG_SHIFT: Final[int] = 28
"""Bit position of the tag inside the unscrambled 32-bit value."""
TAG_MASK: Final[int] = 15
"""Mask for the 4-bit tag field."""
PAYLOAD_MASK: Final[int] = (1 << 28) - 1
"""Mask for the 28-bit payload field."""
TAG_SYMMETRY: Final[int] = 0
"""
Tag for `MarkerSymmetry` (matches Python `_registry` order: 0 = first
subclass to be declared).
"""

"""A marker payload exchanged between friendly units via on-tile markers."""
@dataclass(frozen=True, slots=True)
class MarkerSymmetry:
    """Sender has resolved (or is asserting) the map's symmetry."""
    symmetry: Symmetry

    def encode(self):
        """Encode to the wire `u32` (tag-prefixed, then XOR-scrambled with `KEY`)."""
        match self:
            case MarkerSymmetry(symmetry=symmetry):
                tag, payload = (0, int(symmetry))
        raw = tag << 28 | payload & PAYLOAD_MASK
        return raw ^ 3735928559

    @staticmethod
    def decode(encrypted):
        """
        Decode a wire `u32` back to a `Marker`. Returns `None` if the tag is
        unknown (e.g. emitted by an enemy or an older bot version).
        """
        raw = encrypted ^ 3735928559
        tag = raw >> 28 & 15
        payload = raw & PAYLOAD_MASK
        if tag == 0:
            match payload & 3:
                case 0:
                    sym = Symmetry.Rot
                case 1:
                    sym = Symmetry.Hor
                case 2:
                    sym = Symmetry.Ver
                case _:
                    return None
            return MarkerSymmetry(symmetry=sym)
        else:
            return None

Marker = MarkerSymmetry

def find_symmetry_marker(ct, nearby_tiles, my_team):
    """
    Scan `nearby_tiles` for an allied `MarkerSymmetry` and return its symmetry.
    Returns the first one found, or `None` if no friendly symmetry marker is
    in vision.
    """
    for pos in nearby_tiles:
        bid = ct.get_tile_building_id(pos)
        if bid is None:
            continue
        if ct.get_entity_type(bid) != EntityType.MARKER:
            continue
        if ct.get_team(bid) != my_team:
            continue
        value = ct.get_marker_value(bid)
        __opt_MarkerSymmetry = Marker.decode(value)
        symmetry = __opt_MarkerSymmetry.symmetry if isinstance(__opt_MarkerSymmetry, MarkerSymmetry) else None
        if isinstance(__opt_MarkerSymmetry, MarkerSymmetry):
            return symmetry
    return None
