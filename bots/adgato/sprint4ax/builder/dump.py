from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder

__all__ = ["dump"]


def dump(self: Builder, _ct: Controller) -> None:
    pass
