"""Typed turn objects — clear contract between tasks and executor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from builder.action import Action
    from cambc import Direction


@dataclass(frozen=True, slots=True)
class Wait:
    """Hold position intentionally. Don't fall through to lower tasks."""


@dataclass(frozen=True, slots=True)
class MoveOnly:
    direction: Direction


@dataclass(frozen=True, slots=True)
class ActionOnly:
    action: Action


@dataclass(frozen=True, slots=True)
class ActionMove:
    """Build first, then step."""

    action: Action
    direction: Direction


@dataclass(frozen=True, slots=True)
class MoveAction:
    """Step first, then build."""

    direction: Direction
    action: Action


type Turn = Wait | MoveOnly | ActionOnly | ActionMove | MoveAction
