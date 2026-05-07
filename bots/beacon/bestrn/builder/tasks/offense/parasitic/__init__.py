"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/offense/parasitic/`.

Parasitic-attack subtree: walk toward an enemy harvester / cached
target / enemy conveyor and fire from adjacent tiles. Last-resort
offense once the cheap fire / turret / push branches have all rejected.
"""

from __future__ import annotations

from typing import Final

from builder.tasks._policy import Policy, PolicyGroup, PolicyLeaf, TaskGroup

from . import approach_harvester, chew_conveyor, walk_to_cached_target

OFFENSE_PARASITIC_CHILDREN: Final[list[Policy]] = [
    PolicyLeaf(name="approach_harvester", fn_=approach_harvester.approach_harvester),
    PolicyLeaf(
        name="walk_to_cached_target", fn_=walk_to_cached_target.walk_to_cached_target
    ),
    PolicyLeaf(name="chew_conveyor", fn_=chew_conveyor.chew_conveyor),
]
OFFENSE_PARASITIC_GROUP_INNER: TaskGroup = TaskGroup(
    name="parasitic", children=OFFENSE_PARASITIC_CHILDREN, gate=None
)
OFFENSE_PARASITIC_GROUP: Policy = PolicyGroup(_0=OFFENSE_PARASITIC_GROUP_INNER)
