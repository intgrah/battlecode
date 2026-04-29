"""Tree-structured task policy framework.

Each role's POLICIES entry is a `TaskGroup`: a tree where leaves are
`(self, ct) -> None` functions and internal nodes group siblings under
a common name (and optional gate). The runner does depth-first
traversal; the first leaf that doesn't raise `TaskRejectedError` claims
the turn. See `_policy.py` for `TaskGroup` and `run_policy`.
"""

from builder.role import Role
from builder.tasks._policy import Policy
from builder.tasks.defense import DEFENSE_GROUP
from builder.tasks.econ import ECON_GROUP
from builder.tasks.offense import OFFENSE_GROUP

POLICIES: dict[Role, Policy] = {
    Role.OFFENSE: OFFENSE_GROUP,
    Role.ECON: ECON_GROUP,
    Role.DEFENSE: DEFENSE_GROUP,
    Role.PERM_ECON: ECON_GROUP,
    Role.PERM_DEFENSE: DEFENSE_GROUP,
}
