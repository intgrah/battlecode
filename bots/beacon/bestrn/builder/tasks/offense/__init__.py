"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/offense/`.

Offense role policy trees.
"""

from __future__ import annotations

from typing import Final

from builder.tasks._policy import Policy, TaskGroup, PolicyGroup, PolicyLeaf
from builder.tasks.offense.fire_on_enemy_tile import fire_on_enemy_tile
from builder.tasks.offense.parasitic import OFFENSE_PARASITIC_GROUP
from builder.tasks.offense.push import OFFENSE_PUSH_GROUP
from builder.tasks.offense.scout_toward_enemy import scout_toward_enemy
from builder.tasks.offense.turret_around_harvester import turret_around_harvester
from builder.tasks.shared.deny_enemy_ore import deny_enemy_ore
from builder.tasks.shared.heal import HEAL_GROUP

PUSH_ROLE_CHILDREN: Final[list[Policy]] = [
    HEAL_GROUP,
    PolicyLeaf(name="fire_on_enemy_tile", fn_=fire_on_enemy_tile),
    PolicyLeaf(name="turret_around_harvester", fn_=turret_around_harvester),
    OFFENSE_PUSH_GROUP,
    PolicyLeaf(name="deny_enemy_ore", fn_=deny_enemy_ore),
    PolicyLeaf(name="scout_toward_enemy", fn_=scout_toward_enemy),
]
PUSH_ROLE_GROUP_INNER: TaskGroup = TaskGroup(
    name="push", children=PUSH_ROLE_CHILDREN, gate=None
)
PUSH_ROLE_GROUP: Policy = PolicyGroup(_0=PUSH_ROLE_GROUP_INNER)
PARASITIC_ROLE_CHILDREN: Final[list[Policy]] = [
    HEAL_GROUP,
    PolicyLeaf(name="fire_on_enemy_tile", fn_=fire_on_enemy_tile),
    PolicyLeaf(name="turret_around_harvester", fn_=turret_around_harvester),
    OFFENSE_PARASITIC_GROUP,
    PolicyLeaf(name="deny_enemy_ore", fn_=deny_enemy_ore),
    PolicyLeaf(name="scout_toward_enemy", fn_=scout_toward_enemy),
]
PARASITIC_ROLE_GROUP_INNER: TaskGroup = TaskGroup(
    name="parasitic", children=PARASITIC_ROLE_CHILDREN, gate=None
)
PARASITIC_ROLE_GROUP: Policy = PolicyGroup(_0=PARASITIC_ROLE_GROUP_INNER)
