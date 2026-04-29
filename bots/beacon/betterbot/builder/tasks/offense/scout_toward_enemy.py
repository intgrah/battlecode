"""Terminal OFFENSE fallback. Wraps `offense_helpers.scout_toward_enemy`
as a Task. Never rejects — guarantees the OFFENSE policy always produces
some movement, even when no harvester / cached target / conveyor target
is available.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from builder.tasks.offense.helpers import scout_toward_enemy as _scout

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


def scout_toward_enemy(self: Builder, ct: Controller) -> None:
    """Terminal fallback for OFFENSE — never rejects. Walks toward
    `en_core` until seen, then explores or wanders.
    """
    _scout(self, ct)
