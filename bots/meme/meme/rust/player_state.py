from __future__ import annotations

from rust.base import RustStruct, i32


class PlayerState(RustStruct):
    """PlayerState (20 B): source-order layout."""

    titanium = i32(0)
    axionite = i32(4)
    titanium_collected = i32(8)
    axionite_collected = i32(12)
    scale_milli = i32(16)
