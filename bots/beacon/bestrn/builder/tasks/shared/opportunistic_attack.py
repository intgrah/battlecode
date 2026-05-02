"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/shared/opportunistic_attack.py`.

Cheap, low-priority opportunistic fire used by ECON / DEFENSE roles.
A small fraction of builders (`self.opportunistic` set at init) randomly
fire (p=0.2) on the enemy building under their feet, but only after round
100. Distinct from OFFENSE's structured attack cascade — this is just
"if standing on an enemy thing, occasionally hit it".
"""
from __future__ import annotations

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cambc import Controller, ControllerApi
if TYPE_CHECKING:
    from builder import Builder
from builder.tasks.rejected import TaskRejected
if TYPE_CHECKING:
    from builder.tasks.rejected import TaskResult

def opportunistic_attack(self_, ct):
    if not self_.opportunistic:
        return TaskRejected("builder is not in opportunistic mode")
    r = self_.rng.random()
    if r >= 0.2:
        return TaskRejected("random gate (p=0.2) declined")
    if self_.round <= 100:
        return TaskRejected.from_string(f"round {self_.round} <= 100")
    if not ct.can_fire(self_.my_pos):
        return TaskRejected("ct.can_fire(my_pos) is False")
    bid = ct.get_tile_building_id(self_.my_pos)
    if ct.get_team(bid) == self_.my_team:
        return TaskRejected("tile under builder holds a friendly building")
    ct.fire(self_.my_pos)
    return None
