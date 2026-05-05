from __future__ import annotations

from rust.base import RustStruct, i32


class Pos(RustStruct):
    """Pos { x: i32, y: i32 } — x@0, y@4."""

    x = i32(0)
    y = i32(4)
