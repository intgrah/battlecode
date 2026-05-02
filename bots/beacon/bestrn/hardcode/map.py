"""
Stub for `bots/intgrah/v54.7.9/hardcode/map.py`.

Phase E will replace this with the precomputed lookup table. For now,
callers gate on `HARDCODE` and never reach these.
"""
from __future__ import annotations

from typing import Final

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from util.symmetry import Symmetry
SYMMETRY: Final[Symmetry | None] = None
"""Placeholder for the hardcoded `SYMMETRY` table."""
TILES: Final[list[int]] = []
"""Placeholder for the hardcoded `TILES` blob — empty until Phase E lands."""

def decode(_buf, _w, _h):
    """
    Placeholder for `decode(buf, w, h)`. Real impl returns a dense per-tile
    array; stub is unreachable when `HARDCODE` is false.
    """
    return (_ for _ in ()).throw(NotImplementedError())
