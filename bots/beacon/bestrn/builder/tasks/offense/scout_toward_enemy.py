"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/offense/scout_toward_enemy.py`.

Terminal OFFENSE fallback. Wraps `offense::helpers::scout_toward_enemy`
as a Task. Never rejects — guarantees the OFFENSE policy always produces
some movement, even when no harvester / cached target / conveyor target
is available.
"""

from __future__ import annotations

from builder.tasks.offense.helpers import scout_toward_enemy as scout


def scout_toward_enemy(self_, ct) -> None:
    scout(self_, ct)
