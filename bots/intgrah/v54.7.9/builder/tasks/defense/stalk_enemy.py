"""Stalk a visible enemy builder when this bot is the closest friendly
to it. Pure follow — no firing. Cheap structural pressure: an enemy bot
shadowed by ours can't safely commit to a build action without taking
fire from our turret network, and any reposition the enemy makes is
mirrored.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from util.debug import debug as log

from builder.helpers import make_move
from builder.tasks.rejected import Reason, TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller, Position

    from builder import Builder


class TaskRejectedNoEnemyBotError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "no enemy builder in vision"


class TaskRejectedNotClosestError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "another friendly builder is closer to every visible enemy"


def stalk_enemy(self: Builder, ct: Controller) -> None:
    if not self.enemy_bots:
        raise TaskRejectedNoEnemyBotError

    my_pos = self.my_pos
    target: Position | None = None
    target_d = 1 << 30
    for e in self.enemy_bots:
        my_d = (e.x - my_pos.x) * (e.x - my_pos.x) + (e.y - my_pos.y) * (e.y - my_pos.y)
        closer_friend = False
        for f in self.friendly_bots:
            fd = (e.x - f.x) * (e.x - f.x) + (e.y - f.y) * (e.y - f.y)
            if fd < my_d:
                closer_friend = True
                break
        if closer_friend:
            continue
        if my_d < target_d:
            target_d = my_d
            target = e

    if target is None:
        raise TaskRejectedNotClosestError

    log("stalk_enemy: following {target} (d²={d})", target=target, d=target_d)
    make_move(self, ct, target)
