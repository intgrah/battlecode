"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/offense/push/`.

Forward-push subtree: drop sentinels on dangling ends, fork the
chain behind them with splitters, plant offensive harvesters on
enemy-side ore, extend chains toward the enemy core. The structural
offensive work — high-value, gated by symmetry being known.
"""

from __future__ import annotations

from typing import Final

from . import build_offensive_harvester
from . import claim_offensive_ore
from . import place_offensive_sentinel
from . import push_extend
from . import split_before_sentinel
from builder.tasks._policy import Policy, TaskGroup, PolicyGroup, PolicyLeaf

OFFENSE_PUSH_CHILDREN: Final[list[Policy]] = [
    PolicyLeaf(name="claim_offensive_ore", fn_=claim_offensive_ore.claim_offensive_ore),
    PolicyLeaf(
        name="place_offensive_sentinel",
        fn_=place_offensive_sentinel.place_offensive_sentinel,
    ),
    PolicyLeaf(
        name="split_before_sentinel", fn_=split_before_sentinel.split_before_sentinel
    ),
    PolicyLeaf(
        name="build_offensive_harvester",
        fn_=build_offensive_harvester.build_offensive_harvester,
    ),
    PolicyLeaf(name="push_extend", fn_=push_extend.push_extend),
]
OFFENSE_PUSH_GROUP_INNER: TaskGroup = TaskGroup(
    name="push", children=OFFENSE_PUSH_CHILDREN, gate=None
)
OFFENSE_PUSH_GROUP: Policy = PolicyGroup(_0=OFFENSE_PUSH_GROUP_INNER)
