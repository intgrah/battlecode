from __future__ import annotations

from typing import TYPE_CHECKING

from .flow import FLOW_AX, FLOW_RAX, FLOW_TI

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder

__all__ = ["dump"]


def dump(self: Builder, _ct: Controller) -> None:
    pass
