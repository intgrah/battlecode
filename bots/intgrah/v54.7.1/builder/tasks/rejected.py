from __future__ import annotations

from typing import TYPE_CHECKING, override

if TYPE_CHECKING:
    from cambc import EntityType


class TaskRejectedError(Exception):
    """Base: a task cannot fire this turn. Subclasses carry structured data
    and implement `__str__` for logging. Each task defines its own subclasses
    locally; only genuinely shared ones live in this module."""


class TaskRejectedCannotAffordError(TaskRejectedError):
    def __init__(self, entity: EntityType, have: int, need: int) -> None:
        self.entity = entity
        self.have = have
        self.need = need

    @override
    def __str__(self) -> str:
        return f"{self.entity.name}: have {self.have} ti, need {self.need}"
