"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/econ/infrastructure/build_foundry.py`.

Replace a designated Ti conveyor (`foundry_target`) with a foundry
once its Ax feed is established. Gated on round >= `FOUNDRY_ROUND_GATE`.
Checks the target is still a friendly pure conveyor, that an Ax cardinal
feeds it, and that we can afford the build; walks adjacent and destroys-
then-builds the foundry.
"""
from __future__ import annotations

from typing import Final

from cambc import EntityType, Environment
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cambc import Controller, ControllerApi
if TYPE_CHECKING:
    from builder import Builder
from builder.helpers import ax_feeds_target, can_afford, make_move, try_place
from builder.tasks.rejected import TaskRejected
if TYPE_CHECKING:
    from builder.tasks.rejected import TaskResult
from util.debug import debug as log
FOUNDRY_ROUND_GATE: Final[int] = 500
"""First foundry >= turn 500."""

def build_foundry(self_, ct):
    if self_.round < 500:
        return TaskRejected.from_string(f"round {self_.round} < gate {500}")
    target = self_.foundry_target
    if target is None:
        return TaskRejected("foundry_target is None")
    kind = self_.building_kind[self_.idx(target)]
    team = self_.building_team[self_.idx(target)]
    is_conveyor = ((kind is not None) and (kind == EntityType.CONVEYOR or kind == EntityType.ARMOURED_CONVEYOR))
    if not is_conveyor:
        return TaskRejected.from_string(f"{target!r}: got {kind!r}, expected Ti conveyor")
    if team != self_.my_team:
        return TaskRejected.from_string(f"{target!r}: conveyor held by enemy team")
    if self_.env[self_.idx(target)] != Environment.EMPTY:
        return TaskRejected.from_string(f"{target!r}: terrain is {self_.env[self_.idx(target)]!r}, not EMPTY")
    if not ax_feeds_target(self_, target):
        return TaskRejected.from_string(f"ax chain hasn't reached {target!r}")
    dist_sq = self_.my_pos.distance_squared(target)
    if not can_afford(self_, EntityType.FOUNDRY):
        if dist_sq <= 2:
            log(f"build_foundry: holding {target!r} until affordable", {})
            return None
        log(f"build_foundry: walking toward {target!r}, can't afford yet", {})
        make_move(self_, ct, target)
        return None
    if self_.my_pos == target:
        dirs = list(self_.dir_neighbours_4)
        moved = False
        for d, _npos in dirs:
            if ct.can_move(d):
                ct.move(d)
                moved = True
                break
        if not moved:
            log(f"build_foundry: stuck on {target!r}, cannot step off this turn", {})
            return None
    uid = self_.all_bots.get(target)
    if uid is not None and (uid != self_.my_id):
        log(f"build_foundry: {target!r} occupied by friendly bot, holding", {})
        return None
    if self_.my_pos.distance_squared(target) <= 2 and try_place(self_, ct, EntityType.FOUNDRY, target, None, True):
        log(f"build_foundry: PLACED at {target!r}", {})
        return None
    log(f"build_foundry: out of range of {target!r}, walking", {})
    make_move(self_, ct, target)
    return None
