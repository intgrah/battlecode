from __future__ import annotations

from rust.base import RustStruct


class GameDiffVariant(RustStruct):
    """
    Common base for all `GameDiff` variants.

    Each variant subclass exposes its payload fields via descriptors.
    Subclasses override `__repr__`.
    """

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"
