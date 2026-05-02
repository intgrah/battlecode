"""Offense role policy trees.

Two role-level groups, one per offensive sub-role:

  PUSH role: HEAL → fire_on_enemy_tile → turret_around_harvester →
             OFFENSE_PUSH_GROUP → deny_enemy_ore → scout_toward_enemy
  PARASITIC role: HEAL → fire_on_enemy_tile → turret_around_harvester →
             OFFENSE_PARASITIC_GROUP → deny_enemy_ore → scout_toward_enemy

The shared head (heal / fire / turret) and tail (deny_enemy_ore / scout)
are present in both. Only the middle sub-group differs: a PUSH bot
runs the push tree, a PARASITIC bot runs the parasitic tree.
"""

from builder.tasks._policy import TaskGroup
from builder.tasks.offense.fire_on_enemy_tile import fire_on_enemy_tile
from builder.tasks.offense.parasitic import OFFENSE_PARASITIC_GROUP
from builder.tasks.offense.push import OFFENSE_PUSH_GROUP
from builder.tasks.offense.scout_toward_enemy import scout_toward_enemy
from builder.tasks.offense.turret_around_harvester import turret_around_harvester
from builder.tasks.shared.deny_enemy_ore import deny_enemy_ore
from builder.tasks.shared.heal import HEAL_GROUP

PUSH_ROLE_GROUP = TaskGroup(
    name="push",
    children=(
        HEAL_GROUP,
        fire_on_enemy_tile,
        turret_around_harvester,
        OFFENSE_PUSH_GROUP,
        deny_enemy_ore,
        scout_toward_enemy,
    ),
)

PARASITIC_ROLE_GROUP = TaskGroup(
    name="parasitic",
    children=(
        HEAL_GROUP,
        fire_on_enemy_tile,
        turret_around_harvester,
        OFFENSE_PARASITIC_GROUP,
        deny_enemy_ore,
        scout_toward_enemy,
    ),
)
