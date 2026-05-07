"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/econ/chains/extend_chain_in_range.py`.

Lay a conveyor segment from `dangling_output` toward its sink, only
when the dangling end is within builder vision. The cached
`dangling_output` is refreshed every turn by `update_dangling` (no
stickiness), and the proximity gate inside the picker ensures only the
rightful claimant builder considers a given end.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Controller, ControllerApi
if TYPE_CHECKING:
    from builder import Builder
from builder.chain_routing import extend_chain
from builder.tasks.rejected import TaskRejected

if TYPE_CHECKING:
    from builder.tasks.rejected import TaskResult


def extend_chain_in_range(self_, ct):
    dangling = self_.dangling_output
    if dangling is None:
        return TaskRejected("no dangling output")
    if not ct.is_in_vision(dangling):
        return TaskRejected.from_string(f"dangling {dangling!r} not in vision")
    return extend_chain(self_, ct, dangling)
