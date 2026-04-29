"""Walk toward `dangling_output` and lay a conveyor segment along the
A* path to its sink (Ti -> ti_sink, Ax -> ax_sink). No range gate — the
builder will travel as far as needed. Fires only when the in-range
variant rejects (dangling end out of vision). The cached
`dangling_output` is refreshed every turn by `update_dangling` (no
stickiness).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from builder.chain_routing import extend_chain
from builder.tasks.rejected import Reason, TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


class TaskRejectedNoDanglingOutputError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "no dangling output"


def extend_chain_approach(self: Builder, ct: Controller) -> None:
    if self.dangling_output is None:
        raise TaskRejectedNoDanglingOutputError
    extend_chain(self, ct, self.dangling_output)
