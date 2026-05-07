"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/offense/push/claim_offensive_ore.py`.

Walk onto `offensive_ore_target` (enemy-side ore picked by the
inverse-bisector gate) to claim it. Mirrors `claim_ore` but uses the
offense-specific target.
"""

from __future__ import annotations

from builder.harvest import walk_to_ore_claim
from builder.helpers import ore_available
from builder.tasks.rejected import TaskRejected


def claim_offensive_ore(self_, ct):
    target = self_.offensive_ore_target
    if target is None:
        return TaskRejected("offensive_ore_target is None")
    if self_.my_pos == target:
        return TaskRejected.from_string(f"already on offensive ore {target!r}")
    if not ore_available(self_, target):
        return TaskRejected.from_string(f"offensive ore {target!r} unavailable")
    if not walk_to_ore_claim(self_, ct, target):
        return TaskRejected.from_string(f"no progress toward {target!r}")
    return None
