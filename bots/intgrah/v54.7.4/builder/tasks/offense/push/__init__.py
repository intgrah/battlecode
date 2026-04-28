"""Forward-push subtree: drop sentinels on dangling ends, fork the
chain behind them with splitters, plant offensive harvesters on
enemy-side ore, extend chains toward the enemy core. The structural
offensive work — high-value, gated by symmetry being known.
"""

from builder.tasks._policy import TaskGroup
from builder.tasks.offense.push.place_offensive_harvester import (
    place_offensive_harvester,
)
from builder.tasks.offense.push.place_offensive_sentinel import (
    place_offensive_sentinel,
)
from builder.tasks.offense.push.push_extend import push_extend
from builder.tasks.offense.push.split_before_sentinel import split_before_sentinel

OFFENSE_PUSH_GROUP = TaskGroup(
    name="push",
    children=(
        place_offensive_sentinel,
        split_before_sentinel,
        place_offensive_harvester,
        push_extend,
    ),
)
