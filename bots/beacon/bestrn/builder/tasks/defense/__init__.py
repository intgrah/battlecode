"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/defense/`.

DEFENSE role policy tree.
"""

from __future__ import annotations

from typing import Final

from builder.tasks._policy import Policy, TaskGroup, PolicyGroup, PolicyLeaf
from builder.tasks.defense.patrol_cheap import patrol_cheap
from builder.tasks.defense.patrol_late import patrol_late
from builder.tasks.defense.stalk_enemy import stalk_enemy
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

DEFENSE_CHILDREN: Final[list[Policy]] = [
    ECON_INFRASTRUCTURE_GROUP,
    PolicyLeaf(name="extend_chain_in_range", fn_=extend_chain_in_range),
    HEAL_GROUP,
    PolicyLeaf(name="stalk_enemy", fn_=stalk_enemy),
    PolicyLeaf(name="deny_enemy_ore", fn_=deny_enemy_ore),
    PolicyLeaf(name="patrol_cheap", fn_=patrol_cheap),
    PolicyLeaf(name="claim_ore", fn_=claim_ore),
    PolicyLeaf(name="build_harvester", fn_=build_harvester),
    PolicyLeaf(name="extend_chain_approach", fn_=extend_chain_approach),
    PolicyLeaf(name="patrol_late", fn_=patrol_late),
    PolicyLeaf(name="opportunistic_attack", fn_=opportunistic_attack),
    PolicyLeaf(name="explore", fn_=explore),
    PolicyLeaf(name="wander", fn_=wander),
]
DEFENSE_GROUP_INNER: TaskGroup = TaskGroup(
    name="defense", children=DEFENSE_CHILDREN, gate=None
)
DEFENSE_GROUP: Policy = PolicyGroup(_0=DEFENSE_GROUP_INNER)
