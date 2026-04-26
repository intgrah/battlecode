"""Base exception class for task rejection plus shared subclasses. Tasks
raise these when preconditions don't hold; the policy runner catches
TaskRejectedError and renders it via `reason()` — a (tmpl, args) pair
that doubles as both a typed debug-msg payload (rich widgets for
Positions etc. in the viewer) and a plain `__str__` (when debug is off
or for ordinary tracebacks).

Subclasses override `reason()` to declare the template and named args.
They get `__str__` for free.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, override

if TYPE_CHECKING:
    from cambc import EntityType


type Reason = str | tuple[str, dict[str, object]]


class TaskRejectedError(Exception):
    """Base: a task cannot fire this turn. Subclasses MUST implement
    `reason()`; the base provides `__str__` derived from it.

    `reason()` returns either:
      - a bare template string (no args), or
      - `tmpl, {name: value}` — args substituted into `{name}` slots.
    """

    @abstractmethod
    def reason(self) -> Reason: ...

    @override
    def __str__(self) -> str:
        match self.reason():
            case str(r):
                return r
            case tmpl, args:
                return tmpl.format(**args)


class TaskRejectedCannotAffordError(TaskRejectedError):
    def __init__(self, entity: EntityType, have: int, need: int) -> None:
        self.entity = entity
        self.have = have
        self.need = need

    @override
    def reason(self) -> Reason:
        return "{entity}: have {have} ti, need {need}", {
            "entity": self.entity,
            "have": self.have,
            "need": self.need,
        }
