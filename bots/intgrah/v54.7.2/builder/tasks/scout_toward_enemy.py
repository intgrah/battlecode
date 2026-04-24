from __future__ import annotations

from typing import TYPE_CHECKING

from builder.tasks.offense_helpers import scout_toward_enemy as _scout

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


def scout_toward_enemy(self: Builder, ct: Controller) -> None:
    """Terminal fallback for OFFENSE — never rejects. Walks toward
    `en_core` until seen, then explores or wanders."""
    _scout(self, ct)
