"""DEFENSE role policy tree.

Order (preserved from the original flat list — patrol_cheap and
patrol_late wrap the harvester pair):
  INFRASTRUCTURE group
  EXTEND_CHAIN_IN_RANGE
  HEAL                    (shared)
  DENY_ENEMY_ORE          (shared)
  EXTEND_CHAIN_APPROACH
  PATROL_CHEAP
  HARVEST_TI
  HARVEST_AX
  PATROL_LATE
  OPPORTUNISTIC_ATTACK    (shared)
  EXPLORE                 (shared)
  WANDER                  (shared)
"""

from builder.tasks._policy import TaskGroup
from builder.tasks.defense.patrol_cheap import patrol_cheap
from builder.tasks.defense.patrol_late import patrol_late
from builder.tasks.econ.chains.extend_chain_approach import extend_chain_approach
from builder.tasks.econ.chains.extend_chain_in_range import extend_chain_in_range
from builder.tasks.econ.harvesters.harvest_ax import harvest_ax
from builder.tasks.econ.harvesters.harvest_ti import harvest_ti
from builder.tasks.econ.infrastructure import ECON_INFRASTRUCTURE_GROUP
from builder.tasks.shared.deny_enemy_ore import deny_enemy_ore
from builder.tasks.shared.explore import explore
from builder.tasks.shared.heal import HEAL_GROUP
from builder.tasks.shared.opportunistic_attack import opportunistic_attack
from builder.tasks.shared.wander import wander

DEFENSE_GROUP = TaskGroup(
    name="defense",
    children=(
        ECON_INFRASTRUCTURE_GROUP,
        extend_chain_in_range,
        HEAL_GROUP,
        deny_enemy_ore,
        extend_chain_approach,
        patrol_cheap,
        harvest_ti,
        harvest_ax,
        patrol_late,
        opportunistic_attack,
        explore,
        wander,
    ),
)
