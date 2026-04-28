"""Parasitic-attack subtree: walk toward an enemy harvester / cached
target / enemy conveyor and fire from adjacent tiles. Last-resort
offense once the cheap fire / turret / push branches have all rejected.
"""

from builder.tasks._policy import TaskGroup
from builder.tasks.offense.parasitic.approach_harvester import approach_harvester
from builder.tasks.offense.parasitic.chew_conveyor import chew_conveyor
from builder.tasks.offense.parasitic.walk_to_cached_target import walk_to_cached_target

OFFENSE_PARASITIC_GROUP = TaskGroup(
    name="parasitic",
    children=(approach_harvester, walk_to_cached_target, chew_conveyor),
)
