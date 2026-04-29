"""DEFENSE role policy tree.

Order:
  INFRASTRUCTURE group
  EXTEND_CHAIN_IN_RANGE
  HEAL                    (shared)
  DENY_ENEMY_ORE          (shared)
  PATROL_CHEAP
  CLAIM_ORE              (walk onto the ore — first of three split phases)
  BUILD_HARVESTER        (step off + place harvester — second / last)
  EXTEND_CHAIN_APPROACH  (far chain travel below claiming a closer ore)
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
from builder.tasks.econ.infrastructure import ECON_INFRASTRUCTURE_GROUP
from builder.tasks.econ.ore.build_harvester import build_harvester
from builder.tasks.econ.ore.claim_ore import claim_ore
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
        patrol_cheap,
        claim_ore,
        build_harvester,
        extend_chain_approach,
        patrol_late,
        opportunistic_attack,
        explore,
        wander,
    ),
)
