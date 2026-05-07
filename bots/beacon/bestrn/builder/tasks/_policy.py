"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/_policy.py`.

Tree-structured policy primitives.

A `Policy` is either a `TaskGroup` (an internal node with named children
and an optional gate) or a leaf function `LeafFn` of shape
`(Builder, Controller) -> TaskResult`. Leaves either complete the turn
(return `None`) or return `Err(TaskRejected)` to defer to the next
sibling.

Traversal: depth-first, first-success-wins. `run_policy` returns true
iff some leaf in the subtree completed without rejecting; false iff
every leaf rejected (or the group's gate denied the subtree). The
caller's parent group treats a false return the same way it treats a
leaf rejection — move on to the next sibling.
"""

from __future__ import annotations

from dataclasses import dataclass

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Controller
if TYPE_CHECKING:
    from builder import Builder
if TYPE_CHECKING:
    from builder.tasks.rejected import TaskResult
from util.debug import Scope, debug as log

type LeafFn = Callable[[Builder, Controller], TaskResult]
type Gate = Callable[[Builder, Controller], bool]


class TaskGroup:
    """
    Internal policy node. `children` is searched in order; `gate`, if set,
    can short-circuit the entire subtree when its precondition doesn't
    hold (cheaper than rejecting at every leaf separately).
    """

    name: str
    children: list[Policy]
    gate: Gate | None

    def __init__(self, name: str, children: list[Policy], gate: Gate | None):
        self.name = name
        self.children = children
        self.gate = gate


@dataclass(frozen=True, slots=True)
class PolicyGroup:
    _0: TaskGroup


@dataclass(frozen=True, slots=True)
class PolicyLeaf:
    name: str
    fn_: LeafFn


type Policy = PolicyGroup | PolicyLeaf


def run_policy(self_, ct, policy):
    match policy:
        case PolicyGroup(_0=group):
            gate = group.gate
            if gate is not None and (not gate(self_, ct)):
                args = {}
                args[str("name")] = str(group.name)
                log("{name}: gated off", args)
                return False
            with Scope.new_timed(group.name) as _scope:
                for child in group.children:
                    if run_policy(self_, ct, child):
                        return True
                return False
        case PolicyLeaf(name=name, fn_=fn_):
            scope_label = f"task={name}"
            with Scope.new_timed(scope_label) as _scope:
                match fn_(self_, ct):
                    case None:
                        return True
                    case rej if rej is not None:
                        args = {}
                        args[str("name")] = str(name)
                        args[str("reason")] = rej.reason
                        log("{name}: {reason}", args)
                        return False
