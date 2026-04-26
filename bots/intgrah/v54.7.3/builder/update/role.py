from __future__ import annotations

from typing import TYPE_CHECKING

from builder.role import Role

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


def update_role(self: Builder, _ct: Controller) -> None:
    """Simplified: every builder is an econ builder. Defense and offense
    bots are disabled for now so econ behaviour can be observed in isolation."""
    self.role = Role.ECON
    self.role_age += 1
