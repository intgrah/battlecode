"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/`.

Tree-structured task policy framework.

Each role's POLICIES entry is a `TaskGroup`: a tree where leaves are
`(self, ct) -> TaskResult` functions and internal nodes group siblings under
a common name (and optional gate). The runner does depth-first
traversal; the first leaf that doesn't reject claims the turn. See
`_policy.rs` for `TaskGroup` and `run_policy`.
"""

from __future__ import annotations

from builder.role import Role
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from builder.tasks._policy import Policy, PolicyGroup, PolicyLeaf
from builder.tasks.defense import DEFENSE_GROUP
from builder.tasks.econ import ECON_GROUP
from builder.tasks.offense import PARASITIC_ROLE_GROUP, PUSH_ROLE_GROUP


def policy_for_role(role):
    """Resolve a role to its top-level policy tree."""
    match role:
        case Role.Push:
            return PUSH_ROLE_GROUP
        case Role.Parasitic:
            return PARASITIC_ROLE_GROUP
        case Role.Econ | Role.EconReactive | Role.PermEcon:
            return ECON_GROUP
        case Role.Defense | Role.PermDefense:
            return DEFENSE_GROUP
