"""ECON role policy tree.

Order:
  INFRASTRUCTURE group   (build_foundry, place_gunner, fix_enemy_conveyor,
                          pave_inward_conveyors, resolve_congestion)
  EXTEND_CHAIN_IN_RANGE
  HEAL                    (shared)
  DENY_ENEMY_ORE          (shared)
  CLAIM_ORE              (walk onto the ore — first of three split phases)
  BUILD_HARVESTER        (step off + place harvester — second / last)
  EXTEND_CHAIN_APPROACH  (only travel to a far dangling end if no closer
                          ore claim is available)
  OPPORTUNISTIC_ATTACK    (shared)
  EXPLORE                 (shared)
  WANDER                  (shared)

`pave_inward_conveyors` is the third phase, but it lives in INFRASTRUCTURE
because it can fire opportunistically on any visible harvester / claim.
Visible chains-in-range and the inward ring strictly outrank starting a
new claim; far chain-extension travel ranks below claiming a new ore so
that builders prefer to convert nearby ore into income before walking
across the map.
"""

from builder.tasks._policy import TaskGroup
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

ECON_GROUP = TaskGroup(
    name="econ",
    children=(
        ECON_INFRASTRUCTURE_GROUP,
        extend_chain_in_range,
        HEAL_GROUP,
        deny_enemy_ore,
        claim_ore,
        build_harvester,
        extend_chain_approach,
        opportunistic_attack,
        explore,
        wander,
    ),
)
