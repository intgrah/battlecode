"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/econ/infrastructure/`.

Infrastructure subtree: foundry / turret placement, repair-style
fixes, congestion relief, dead-bridge teardown, harvester-neighbour
paving. High-priority structural maintenance work for ECON / DEFENSE.
"""

from __future__ import annotations

from typing import Final

from . import build_foundry
from . import fix_enemy_conveyor
from . import guard_harvester_neighbours
from . import place_gunner
from . import resolve_congestion
from builder.tasks._policy import Policy, TaskGroup, PolicyGroup, PolicyLeaf

ECON_INFRASTRUCTURE_CHILDREN: Final[list[Policy]] = [
    PolicyLeaf(name="build_foundry", fn_=build_foundry.build_foundry),
    PolicyLeaf(name="place_gunner", fn_=place_gunner.place_gunner),
    PolicyLeaf(name="fix_enemy_conveyor", fn_=fix_enemy_conveyor.fix_enemy_conveyor),
    PolicyLeaf(
        name="guard_harvester_neighbours",
        fn_=guard_harvester_neighbours.guard_harvester_neighbours,
    ),
    PolicyLeaf(name="resolve_congestion", fn_=resolve_congestion.resolve_congestion),
]
ECON_INFRASTRUCTURE_GROUP_INNER: TaskGroup = TaskGroup(
    name="infrastructure", children=ECON_INFRASTRUCTURE_CHILDREN, gate=None
)
ECON_INFRASTRUCTURE_GROUP: Policy = PolicyGroup(_0=ECON_INFRASTRUCTURE_GROUP_INNER)
