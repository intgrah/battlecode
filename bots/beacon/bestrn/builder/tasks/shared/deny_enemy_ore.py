"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/shared/deny_enemy_ore.py`.

Reactively pave a road on a tile cardinal to a spotted enemy ore
deposit, denying them a harvester-feeder slot. Tile candidates come from
`deny_ore_neighbours` (populated by `update_ore_denial`). One road per
turn; rejects if no candidate in vision is buildable right now.
"""

from __future__ import annotations

from cambc import Environment
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Controller, ControllerApi
if TYPE_CHECKING:
    from builder import Builder
from builder.tasks.rejected import TaskRejected

if TYPE_CHECKING:
    from builder.tasks.rejected import TaskResult


def deny_enemy_ore(self_, ct):
    for pos in list(self_.nearby_tiles):
        if (
            (pos in self_.deny_ore_neighbours)
            and self_.env[self_.idx(pos)] != Environment.WALL
            and (self_.get_building(pos) is None)
            and ct.can_build_road(pos)
        ):
            ct.build_road(pos)
            return None
    return TaskRejected("no in-range tile is a denial candidate right now")
