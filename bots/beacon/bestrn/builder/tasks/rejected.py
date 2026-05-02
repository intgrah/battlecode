"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/rejected.py`.

Failure model is Option-shape, not Result: `None` = task fired,
`Some(TaskRejected)` = task rejected. Dodges Python exceptions
(which would be non-deterministic if any unrelated exception
propagated mid-turn) and matches the pyrust DSL `try_!` macro for
early propagation.
"""
from __future__ import annotations

class TaskRejected:
    reason: str

    def __init__(self, reason):
        """Build a rejection from a static reason string."""
        self.reason = str(reason)

    @staticmethod
    def from_string(reason):
        """Build a rejection from an owned reason string (for templated reasons)."""
        __self = TaskRejected.__new__(TaskRejected)
        __self.reason = reason
        return __self

    def fmt(self, f):
        return f.write_str(self.reason)
type TaskResult = TaskRejected | None
