"""Tree-structured policy primitives.

A `Policy` is either a `TaskGroup` (an internal node with named children
and an optional gate) or a leaf function `LeafFn` of shape
`(Builder, Controller) -> None`. Leaves either complete the turn (return
None) or raise `TaskRejectedError` to defer to the next sibling.

Traversal: depth-first, first-success-wins. `run_policy` returns True
iff some leaf in the subtree completed without rejecting; False iff
every leaf rejected (or the group's gate denied the subtree). The
caller's parent group treats a False return the same way it treats a
leaf rejection — move on to the next sibling.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from util.debug import Scope
from util.debug import debug as log

from builder.tasks.rejected import TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder

type LeafFn = Callable[[Builder, Controller], None]
type Gate = Callable[[Builder, Controller], bool]


@dataclass(frozen=True, slots=True)
class TaskGroup:
    """Internal policy node. `children` is searched in order; `gate`, if
    set, can short-circuit the entire subtree when its precondition
    doesn't hold (cheaper than rejecting at every leaf separately)."""

    name: str
    children: tuple[Policy, ...]
    gate: Gate | None = None


type Policy = TaskGroup | LeafFn


def run_policy(self: Builder, ct: Controller, policy: Policy) -> bool:
    match policy:
        case TaskGroup(name=name, children=children, gate=gate):
            if gate is not None and not gate(self, ct):
                log(f"{name}: gated off")
                return False
            with Scope(name):
                for child in children:
                    if run_policy(self, ct, child):
                        return True
            return False
        case fn:
            with Scope(f"task={fn.__name__}"):
                try:
                    fn(self, ct)
                except Exception as exc:
                    if not isinstance(exc, TaskRejectedError):
                        raise
                    r = exc.reason()
                    name = type(exc).__name__
                    if isinstance(r, str):
                        log(f"{name}: {r}" if r else name)
                    else:
                        tmpl, args = r
                        log(f"{name}: {tmpl}", **args)
                    return False
                else:
                    return True
