"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/offense/push/push_extend.py`.

Extend `dangling_output` toward the enemy core (instead of `ti_sink`
or `my_core`). Used after a forward harvester is planted, growing the
offensive chain toward enemy lines. Requires symmetry to be resolved so
`en_core_guess` returns a known position.
"""

from __future__ import annotations

from cambc import ResourceType

from builder.chain_routing import extend_step, resource_at
from builder.helpers import on_enemy_side
from builder.tasks.rejected import TaskRejected


def push_extend(self_, ct):
    if self_.symmetry is None:
        return TaskRejected("symmetry unresolved; en_core unknown")
    start = self_.dangling_output
    if start is None:
        return TaskRejected("no dangling output")
    if not on_enemy_side(self_, start):
        return TaskRejected.from_string(
            f"dangling {start!r} is on our side of the bisector"
        )
    resource = resource_at(self_, start)
    if resource != ResourceType.TITANIUM:
        return TaskRejected.from_string(
            f"dangling {start!r} is {resource!r}, push_extend is Ti-only"
        )
    target = self_.en_core_guess
    return extend_step(self_, ct, start, target, ResourceType.TITANIUM)
