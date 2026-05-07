"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/econ/`.

ECON role policy tree.
"""

from __future__ import annotations

from typing import Final

from builder.tasks._policy import Policy, PolicyGroup, PolicyLeaf, TaskGroup
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

ECON_CHILDREN: Final[list[Policy]] = [
    ECON_INFRASTRUCTURE_GROUP,
    PolicyLeaf(name="extend_chain_in_range", fn_=extend_chain_in_range),
    HEAL_GROUP,
    PolicyLeaf(name="deny_enemy_ore", fn_=deny_enemy_ore),
    PolicyLeaf(name="claim_ore", fn_=claim_ore),
    PolicyLeaf(name="build_harvester", fn_=build_harvester),
    PolicyLeaf(name="extend_chain_approach", fn_=extend_chain_approach),
    PolicyLeaf(name="opportunistic_attack", fn_=opportunistic_attack),
    PolicyLeaf(name="explore", fn_=explore),
    PolicyLeaf(name="wander", fn_=wander),
]
ECON_GROUP_INNER: TaskGroup = TaskGroup(name="econ", children=ECON_CHILDREN, gate=None)
ECON_GROUP: Policy = PolicyGroup(_0=ECON_GROUP_INNER)
