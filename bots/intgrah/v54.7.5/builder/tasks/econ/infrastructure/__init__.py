"""Infrastructure subtree: foundry / turret placement, repair-style
fixes, congestion relief, dead-bridge teardown, harvester-neighbour
paving. High-priority structural maintenance work for ECON / DEFENSE.
"""

from builder.tasks._policy import TaskGroup
from builder.tasks.econ.infrastructure.build_foundry import build_foundry
from builder.tasks.econ.infrastructure.fix_enemy_conveyor import fix_enemy_conveyor
from builder.tasks.econ.infrastructure.pave_near_harvester import pave_near_harvester
from builder.tasks.econ.infrastructure.place_gunner import place_gunner
from builder.tasks.econ.infrastructure.resolve_congestion import resolve_congestion

# `destroy_dead_bridge` is intentionally not in this group. UF-reachability
# gating in conv routing prevents dangling ends from forming on
# unreachable-component tiles in the first place, so the task is dead
# code in v54.7.5+. The module file is kept for reference.

ECON_INFRASTRUCTURE_GROUP = TaskGroup(
    name="infrastructure",
    children=(
        build_foundry,
        place_gunner,
        fix_enemy_conveyor,
        pave_near_harvester,
        resolve_congestion,
    ),
)
