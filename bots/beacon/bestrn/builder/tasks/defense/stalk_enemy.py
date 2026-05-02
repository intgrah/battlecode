"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/defense/stalk_enemy.py`.

Stalk a visible enemy builder when this bot is the closest friendly
to it. Pure follow — no firing. Cheap structural pressure: an enemy bot
shadowed by ours can't safely commit to a build action without taking
fire from our turret network, and any reposition the enemy makes is
mirrored.
"""
from __future__ import annotations

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cambc import Controller, Position
if TYPE_CHECKING:
    from builder import Builder
from builder.helpers import make_move
from builder.tasks.rejected import TaskRejected
if TYPE_CHECKING:
    from builder.tasks.rejected import TaskResult
from util.debug import debug as log
from util.visualiser import auto_wrap_position

def stalk_enemy(self_, ct):
    if (not self_.enemy_bots):
        return TaskRejected("no enemy builder in vision")
    my_pos = self_.my_pos
    target: Position | None = None
    best_key: tuple[int, int, int] = (1 << 30, 0, 0)
    for e in self_.enemy_bots:
        my_d = (e.x - my_pos.x) * (e.x - my_pos.x) + (e.y - my_pos.y) * (e.y - my_pos.y)
        closer_friend = False
        for f in self_.friendly_bots:
            fd = (e.x - f.x) * (e.x - f.x) + (e.y - f.y) * (e.y - f.y)
            if fd < my_d:
                closer_friend = True
                break
        if closer_friend:
            continue
        key = (my_d, e.y, e.x)
        if key < best_key:
            best_key = key
            target = e
    target_d = best_key[0]
    target = target
    if target is None:
        return TaskRejected("another friendly builder is closer to every visible enemy")
    args = {}
    args[str("target")] = auto_wrap_position(target)
    args[str("d")] = target_d
    log("stalk_enemy: following {target} (d²={d})", args)
    make_move(self_, ct, target)
    return None
