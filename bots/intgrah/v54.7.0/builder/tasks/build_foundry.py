from __future__ import annotations

from typing import TYPE_CHECKING, Final, override

from building import BuildingArmouredConveyor, BuildingConveyor
from cambc import Controller, EntityType, Environment, Position
from util.debug import debug as log

from builder.helpers import ax_feeds_target, can_afford, make_move, try_place
from builder.tasks.rejected import TaskRejectedError

if TYPE_CHECKING:
    from building import Building

    from builder import Builder

__all__ = ["build_foundry"]


FOUNDRY_ROUND_GATE: Final = 500
"""First foundry >= turn 500."""


class TaskRejectedFoundryTooEarlyError(TaskRejectedError):
    def __init__(self, current_round: int) -> None:
        self.current_round = current_round

    @override
    def __str__(self) -> str:
        return f"round {self.current_round} < gate {FOUNDRY_ROUND_GATE}"


class TaskRejectedNoFoundryTargetError(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "foundry_target is None"


class TaskRejectedFoundryTargetWrongTypeError(TaskRejectedError):
    def __init__(self, target: Position, got: Building | None) -> None:
        self.target = target
        self.got = got

    @override
    def __str__(self) -> str:
        return f"{self.target}: got {type(self.got).__name__}, expected Ti conveyor"


class TaskRejectedFoundryTargetEnemyError(TaskRejectedError):
    def __init__(self, target: Position) -> None:
        self.target = target

    @override
    def __str__(self) -> str:
        return f"{self.target}: conveyor held by enemy team"


class TaskRejectedFoundryTerrainNotEmptyError(TaskRejectedError):
    def __init__(self, target: Position, env: Environment | None) -> None:
        self.target = target
        self.env = env

    @override
    def __str__(self) -> str:
        return f"{self.target}: terrain is {self.env}, not EMPTY"


class TaskRejectedAxChainNotConnectedError(TaskRejectedError):
    def __init__(self, target: Position) -> None:
        self.target = target

    @override
    def __str__(self) -> str:
        return f"ax chain hasn't reached {self.target}"


def build_foundry(self: Builder, ct: Controller) -> None:
    """Place a foundry at `self.foundry_target` once an Ax-sourced chain
    feeds into it. If affordability is the only blocker, the builder walks
    to the target and waits rather than wandering off (foundries cost more
    than a harvester's worth of Ti and that buffer must not be spent on
    other work while the chain sits idle)."""
    if self.round < FOUNDRY_ROUND_GATE:
        raise TaskRejectedFoundryTooEarlyError(self.round)
    target = self.foundry_target
    if target is None:
        raise TaskRejectedNoFoundryTargetError
    bld = self.get_building(target)
    if not isinstance(bld, BuildingConveyor | BuildingArmouredConveyor):
        raise TaskRejectedFoundryTargetWrongTypeError(target, bld)
    if bld.team != self.my_team:
        raise TaskRejectedFoundryTargetEnemyError(target)
    if self.get_env(target) != Environment.EMPTY:
        raise TaskRejectedFoundryTerrainNotEmptyError(target, self.get_env(target))
    if not ax_feeds_target(self, target):
        raise TaskRejectedAxChainNotConnectedError(target)

    # Chain connected, tile valid. Committed — walk/wait to place.
    dist_sq = self.my_pos.distance_squared(target)
    if not can_afford(self, EntityType.FOUNDRY):
        if dist_sq <= 2:
            log(f"build_foundry: holding {target} until affordable")
            return
        log(f"build_foundry: walking toward {target}, can't afford yet")
        make_move(self, ct, target)
        return

    if self.my_pos == target:
        for d, _npos in self.dir_neighbours_4:
            if ct.can_move(d):
                ct.move(d)
                break
        else:
            log(f"build_foundry: stuck on {target}, cannot step off this turn")
            return

    if target in self.all_bots and self.all_bots[target] != self.my_id:
        log(f"build_foundry: {target} occupied by friendly bot, holding")
        return

    if self.my_pos.distance_squared(target) <= 2 and try_place(
        self,
        ct,
        EntityType.FOUNDRY,
        target,
    ):
        log(f"build_foundry: PLACED at {target}")
        return

    log(f"build_foundry: out of range of {target}, walking")
    make_move(self, ct, target)
