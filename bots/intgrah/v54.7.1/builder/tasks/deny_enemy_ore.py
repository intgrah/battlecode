from __future__ import annotations

from typing import TYPE_CHECKING, override

from cambc import Environment

from builder.tasks.rejected import TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


class TaskRejectedNoDenialCandidateError(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "no in-range tile is a denial candidate right now"


def deny_enemy_ore(self: Builder, ct: Controller) -> None:
    for pos in self.nearby_tiles:
        if (
            pos in self.deny_ore_neighbours
            and self.get_env(pos) != Environment.WALL
            and self.get_building(pos) is None
            and ct.can_build_road(pos)
        ):
            ct.build_road(pos)
            return
    raise TaskRejectedNoDenialCandidateError
