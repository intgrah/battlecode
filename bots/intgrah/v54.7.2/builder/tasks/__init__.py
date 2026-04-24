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
from builder.tasks.approach_harvester import approach_harvester
from builder.tasks.build_foundry import build_foundry
from builder.tasks.chew_conveyor import chew_conveyor
from builder.tasks.deny_enemy_ore import deny_enemy_ore
from builder.tasks.destroy_dead_bridge import destroy_dead_bridge
from builder.tasks.explore import explore
from builder.tasks.extend_chain_approach import extend_chain_approach
from builder.tasks.extend_chain_in_range import extend_chain_in_range
from builder.tasks.fire_on_enemy_tile import fire_on_enemy_tile
from builder.tasks.fix_enemy_conveyor import fix_enemy_conveyor
from builder.tasks.harvest_ax import harvest_ax
from builder.tasks.harvest_ti import harvest_ti
from builder.tasks.heal import heal
from builder.tasks.opportunistic_attack import opportunistic_attack
from builder.tasks.patrol_cheap import patrol_cheap
from builder.tasks.patrol_late import patrol_late
from builder.tasks.pave_near_harvester import pave_near_harvester
from builder.tasks.place_gunner import place_gunner
from builder.tasks.place_offensive_harvester import place_offensive_harvester
from builder.tasks.place_offensive_sentinel import place_offensive_sentinel
from builder.tasks.push_extend import push_extend
from builder.tasks.resolve_congestion import resolve_congestion
from builder.tasks.scout_toward_enemy import scout_toward_enemy
from builder.tasks.split_before_sentinel import split_before_sentinel
from builder.tasks.turret_around_harvester import turret_around_harvester
from builder.tasks.walk_to_cached_target import walk_to_cached_target
from builder.tasks.wander import wander

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


class Task(StrEnum):
    APPROACH_HARVESTER = "approach_harvester"
    BUILD_FOUNDRY = "build_foundry"
    CHEW_CONVEYOR = "chew_conveyor"
    DENY_ENEMY_ORE = "deny_enemy_ore"
    DESTROY_DEAD_BRIDGE = "destroy_dead_bridge"
    EXPLORE = "explore"
    EXTEND_CHAIN_APPROACH = "extend_chain_approach"
    EXTEND_CHAIN_IN_RANGE = "extend_chain_in_range"
    FIRE_ON_ENEMY_TILE = "fire_on_enemy_tile"
    FIX_ENEMY_CONVEYOR = "fix_enemy_conveyor"
    HARVEST_AX = "harvest_ax"
    HARVEST_TI = "harvest_ti"
    HEAL = "heal"
    OPPORTUNISTIC_ATTACK = "opportunistic_attack"
    PATROL_CHEAP = "patrol_cheap"
    PATROL_LATE = "patrol_late"
    PAVE_NEAR_HARVESTER = "pave_near_harvester"
    PLACE_GUNNER = "place_gunner"
    PLACE_OFFENSIVE_HARVESTER = "place_offensive_harvester"
    PLACE_OFFENSIVE_SENTINEL = "place_offensive_sentinel"
    PUSH_EXTEND = "push_extend"
    RESOLVE_CONGESTION = "resolve_congestion"
    SCOUT_TOWARD_ENEMY = "scout_toward_enemy"
    SPLIT_BEFORE_SENTINEL = "split_before_sentinel"
    TURRET_AROUND_HARVESTER = "turret_around_harvester"
    WALK_TO_CACHED_TARGET = "walk_to_cached_target"
    WANDER = "wander"

    def run(self, builder: Builder, ct: Controller) -> None:
        match self:
            case Task.APPROACH_HARVESTER:
                approach_harvester(builder, ct)
            case Task.BUILD_FOUNDRY:
                build_foundry(builder, ct)
            case Task.CHEW_CONVEYOR:
                chew_conveyor(builder, ct)
            case Task.DENY_ENEMY_ORE:
                deny_enemy_ore(builder, ct)
            case Task.DESTROY_DEAD_BRIDGE:
                destroy_dead_bridge(builder, ct)
            case Task.EXPLORE:
                explore(builder, ct)
            case Task.EXTEND_CHAIN_APPROACH:
                extend_chain_approach(builder, ct)
            case Task.EXTEND_CHAIN_IN_RANGE:
                extend_chain_in_range(builder, ct)
            case Task.FIRE_ON_ENEMY_TILE:
                fire_on_enemy_tile(builder, ct)
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
            case Task.PLACE_OFFENSIVE_HARVESTER:
                place_offensive_harvester(builder, ct)
            case Task.PLACE_OFFENSIVE_SENTINEL:
                place_offensive_sentinel(builder, ct)
            case Task.PUSH_EXTEND:
                push_extend(builder, ct)
            case Task.RESOLVE_CONGESTION:
                resolve_congestion(builder, ct)
            case Task.SCOUT_TOWARD_ENEMY:
                scout_toward_enemy(builder, ct)
            case Task.SPLIT_BEFORE_SENTINEL:
                split_before_sentinel(builder, ct)
            case Task.TURRET_AROUND_HARVESTER:
                turret_around_harvester(builder, ct)
            case Task.WALK_TO_CACHED_TARGET:
                walk_to_cached_target(builder, ct)
            case Task.WANDER:
                wander(builder, ct)


POLICIES: dict[Role, list[Task]] = {
    Role.OFFENSE: [
        Task.HEAL,
        Task.FIRE_ON_ENEMY_TILE,
        Task.TURRET_AROUND_HARVESTER,
        Task.PLACE_OFFENSIVE_SENTINEL,
        Task.SPLIT_BEFORE_SENTINEL,
        Task.PLACE_OFFENSIVE_HARVESTER,
        Task.PUSH_EXTEND,
        Task.APPROACH_HARVESTER,
        Task.WALK_TO_CACHED_TARGET,
        Task.CHEW_CONVEYOR,
        Task.DENY_ENEMY_ORE,
        Task.SCOUT_TOWARD_ENEMY,
    ],
    Role.ECON: [
        Task.BUILD_FOUNDRY,
        Task.PLACE_GUNNER,
        Task.FIX_ENEMY_CONVEYOR,
        Task.PAVE_NEAR_HARVESTER,
        Task.RESOLVE_CONGESTION,
        Task.DESTROY_DEAD_BRIDGE,
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
        Task.RESOLVE_CONGESTION,
        Task.DESTROY_DEAD_BRIDGE,
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
