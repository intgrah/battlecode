"""Task framework.

Each task is one `run(self, ct) -> bool` function in its own file. A task:
- returns True when it claims the turn, OR
- raises a `TaskRejected` subclass explaining why it can't fire.

`POLICIES[role]` is a list of `Task` enum members; the runner iterates in
order, invokes `task.run(builder, ct)`, and catches `TaskRejected` to log a
structured reason before moving on.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from builder.role import Role
from builder.tasks.attack import attack
from builder.tasks.build_foundry import build_foundry
from builder.tasks.deny_enemy_ore import deny_enemy_ore
from builder.tasks.explore import explore
from builder.tasks.extend_chain_approach import extend_chain_approach
from builder.tasks.extend_chain_in_range import extend_chain_in_range
from builder.tasks.fix_enemy_conveyor import fix_enemy_conveyor
from builder.tasks.harvest_ax import harvest_ax
from builder.tasks.harvest_ti import harvest_ti
from builder.tasks.heal import heal
from builder.tasks.opportunistic_attack import opportunistic_attack
from builder.tasks.patrol_cheap import patrol_cheap
from builder.tasks.patrol_late import patrol_late
from builder.tasks.pave_near_harvester import pave_near_harvester
from builder.tasks.place_gunner import place_gunner
from builder.tasks.wander import wander

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


class Task(StrEnum):
    ATTACK = "attack"
    BUILD_FOUNDRY = "build_foundry"
    DENY_ENEMY_ORE = "deny_enemy_ore"
    EXPLORE = "explore"
    EXTEND_CHAIN_APPROACH = "extend_chain_approach"
    EXTEND_CHAIN_IN_RANGE = "extend_chain_in_range"
    FIX_ENEMY_CONVEYOR = "fix_enemy_conveyor"
    HARVEST_AX = "harvest_ax"
    HARVEST_TI = "harvest_ti"
    HEAL = "heal"
    OPPORTUNISTIC_ATTACK = "opportunistic_attack"
    PATROL_CHEAP = "patrol_cheap"
    PATROL_LATE = "patrol_late"
    PAVE_NEAR_HARVESTER = "pave_near_harvester"
    PLACE_GUNNER = "place_gunner"
    WANDER = "wander"

    def run(self, builder: Builder, ct: Controller) -> None:
        match self:
            case Task.ATTACK:
                attack(builder, ct)
            case Task.BUILD_FOUNDRY:
                build_foundry(builder, ct)
            case Task.DENY_ENEMY_ORE:
                deny_enemy_ore(builder, ct)
            case Task.EXPLORE:
                explore(builder, ct)
            case Task.EXTEND_CHAIN_APPROACH:
                extend_chain_approach(builder, ct)
            case Task.EXTEND_CHAIN_IN_RANGE:
                extend_chain_in_range(builder, ct)
            case Task.FIX_ENEMY_CONVEYOR:
                fix_enemy_conveyor(builder, ct)
            case Task.HARVEST_AX:
                harvest_ax(builder, ct)
            case Task.HARVEST_TI:
                harvest_ti(builder, ct)
            case Task.HEAL:
                heal(builder, ct)
            case Task.OPPORTUNISTIC_ATTACK:
                opportunistic_attack(builder, ct)
            case Task.PATROL_CHEAP:
                patrol_cheap(builder, ct)
            case Task.PATROL_LATE:
                patrol_late(builder, ct)
            case Task.PAVE_NEAR_HARVESTER:
                pave_near_harvester(builder, ct)
            case Task.PLACE_GUNNER:
                place_gunner(builder, ct)
            case Task.WANDER:
                wander(builder, ct)


POLICIES: dict[Role, list[Task]] = {
    Role.OFFENSE: [
        Task.HEAL,
        Task.DENY_ENEMY_ORE,
        Task.ATTACK,
    ],
    Role.ECON: [
        Task.BUILD_FOUNDRY,
        Task.PLACE_GUNNER,
        Task.FIX_ENEMY_CONVEYOR,
        Task.PAVE_NEAR_HARVESTER,
        Task.EXTEND_CHAIN_IN_RANGE,
        Task.HEAL,
        Task.DENY_ENEMY_ORE,
        Task.EXTEND_CHAIN_APPROACH,
        Task.HARVEST_TI,
        Task.HARVEST_AX,
        Task.OPPORTUNISTIC_ATTACK,
        Task.EXPLORE,
        Task.WANDER,
    ],
    Role.DEFENSE: [
        Task.BUILD_FOUNDRY,
        Task.PLACE_GUNNER,
        Task.FIX_ENEMY_CONVEYOR,
        Task.PAVE_NEAR_HARVESTER,
        Task.EXTEND_CHAIN_IN_RANGE,
        Task.HEAL,
        Task.DENY_ENEMY_ORE,
        Task.EXTEND_CHAIN_APPROACH,
        Task.PATROL_CHEAP,
        Task.HARVEST_TI,
        Task.HARVEST_AX,
        Task.PATROL_LATE,
        Task.OPPORTUNISTIC_ATTACK,
        Task.EXPLORE,
        Task.WANDER,
    ],
}
