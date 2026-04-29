"""Offense role policy tree.

Order:
  HEAL                  (shared)
  FIRE_ON_ENEMY_TILE    (cheap structural pressure)
  TURRET_AROUND_HARVESTER (one-shot high-value)
  PUSH group            (sentinel/split/offensive harvester/push extend)
  PARASITIC group       (approach/walk/chew)
  DENY_ENEMY_ORE        (shared)
  SCOUT_TOWARD_ENEMY    (terminal — never rejects)
"""

from builder.tasks._policy import TaskGroup
from builder.tasks.offense.fire_on_enemy_tile import fire_on_enemy_tile
from builder.tasks.offense.parasitic import OFFENSE_PARASITIC_GROUP
from builder.tasks.offense.push import OFFENSE_PUSH_GROUP
from builder.tasks.offense.scout_toward_enemy import scout_toward_enemy
from builder.tasks.offense.turret_around_harvester import turret_around_harvester
from builder.tasks.shared.deny_enemy_ore import deny_enemy_ore
from builder.tasks.shared.heal import HEAL_GROUP

OFFENSE_GROUP = TaskGroup(
    name="offense",
    children=(
        HEAL_GROUP,
        fire_on_enemy_tile,
        turret_around_harvester,
        OFFENSE_PUSH_GROUP,
        OFFENSE_PARASITIC_GROUP,
        deny_enemy_ore,
        scout_toward_enemy,
    ),
)
