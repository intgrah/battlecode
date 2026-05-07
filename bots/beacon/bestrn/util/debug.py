"""
Translation of `bots/intgrah/v54.7.9/util/debug.py`.

Bot-side debug helpers — structured per-turn JSON tree + cambc indicator
overlays.

Per-turn flow:
- The first `Scope` of the turn starts a fresh root node and stack.
- Nested `Scope`s become child nodes of the current top-of-stack scope.
- Bodies append `msg` and `vis` nodes via `debug()` and `vis()`.
- At end of turn, the bot calls `flush()` which prints the root tree as
  one line of JSON to stdout.

State lives in a `DebugCtx` struct with one process-global instance. Each
cdylib has its own copy of the static, and the engine serialises bot
calls per turn, so no locking is needed in practice — `unsafe` reads from
a `static mut` are fine on this single-threaded path.
"""

from __future__ import annotations

import json
import time
from typing import Final

from config import DEBUG_LOG

from util.visualiser import Dumper

TYPE_KEY: Final[str] = "$type"
"""Discriminator key for typed JSON nodes (matches Python `_TYPE = "$type"`)."""


class Frame:
    """
    Per-frame entry: the index of this scope's child slot inside its parent's
    `children` array, plus (for timed scopes) the start nanosecond timestamp.
    The frame at index 0 has `parent_child_idx = None` because it is the root.
    """

    parent_child_idx: int | None
    t0_ns: int | None

    def __init__(self, parent_child_idx: int | None, t0_ns: int | None) -> None:
        self.parent_child_idx = parent_child_idx
        self.t0_ns = t0_ns


class DebugCtx:
    """Per-bot debug state. One instance per process via `DebugCtx::global()`."""

    root: Value | None
    frames: list[Frame]
    dumper: Dumper
    last_flush_us: int

    def __init__(self) -> None:
        self.root = None
        self.frames = []
        self.dumper = Dumper()
        self.last_flush_us = 0

    def current_scope_mut(self):
        """
        Walk into the current scope node (the deepest open scope), using
        the parent-child indices recorded in `frames`.
        """
        root = self.root
        node: Value = root
        for f in self.frames[1:]:
            idx = f.parent_child_idx
            node = node["children"][idx]
        return node

    def push_scope(self, label, timed) -> None:
        node = {"$type": "scope", "name": str(label), "children": []}
        t0_ns = time.perf_counter_ns() if timed else None
        if self.root is None:
            self.root = node
            self.frames.append(Frame(parent_child_idx=None, t0_ns=t0_ns))
            return
        parent = self.current_scope_mut()
        children = parent["children"]
        idx = len(children)
        children.append(node)
        self.frames.append(Frame(parent_child_idx=idx, t0_ns=t0_ns))

    def pop_scope(self) -> None:
        frame = self.frames.pop() if self.frames else None
        t0_ns = frame.t0_ns
        if t0_ns is not None:
            us = (time.perf_counter_ns() - t0_ns) // 1000
            if not self.frames:
                root = self.root
                root["us"] = us
            else:
                idx = frame.parent_child_idx
                parent = self.current_scope_mut()
                parent["children"][idx]["us"] = us
        if not self.frames:
            self.root = None

    def emit_child(self, node) -> None:
        if not self.frames:
            return
        parent = self.current_scope_mut()
        parent["children"].append(node)

    def debug(self, tmpl, args) -> None:
        node = {"$type": "msg", "tmpl": str(tmpl), "args": args}
        self.emit_child(node)

    def vis(self, name, value) -> None:
        if not self.frames:
            return
        root = self.root
        node: Value = root
        for f in self.frames[1:]:
            idx = f.parent_child_idx
            node = node["children"][idx]
        children = node["children"]
        self.dumper.dump(children, name, value)

    def flush(self) -> None:
        prev_us = self.last_flush_us
        root = self.root
        root["prev_flush_us"] = prev_us
        t0_ns = time.perf_counter_ns()
        payload = json.dumps(root)
        print(f"{payload}")
        self.last_flush_us = (time.perf_counter_ns() - t0_ns) // 1000

    @staticmethod
    def default():
        return DebugCtx()


CTX: DebugCtx | None = None
"""
Process-global debug context. Lazily initialised on first access. Each
cdylib has its own copy of `CTX`, and the engine serialises bot calls
per turn, so the unsynchronised access is safe on the single-threaded
hot path.
"""


def ctx():
    global CTX
    if CTX is None:
        CTX = DebugCtx()
    return CTX


class Scope:
    """
    Tree-internal scope guard. Constructed via `Scope::new` (untimed) or
    `Scope::new_timed` (records `us` elapsed on drop). The constructor pushes
    a `scope` node onto the stack and attaches it to its parent; `Drop` pops
    the stack and records elapsed microseconds if timed.

    pyrust will translate `let _g = Scope::new("foo");` blocks back to Python
    `with Scope("foo"):` blocks (RAII guard ↔ context manager).
    """

    label: str

    def __init__(self, label) -> None:
        """Push an untimed scope onto the stack. The returned guard pops on drop."""
        if DEBUG_LOG:
            ctx().push_scope(label, False)
        self.label = str(label)

    @staticmethod
    def new_timed(label):
        """
        Push a timed scope; on drop, records `us` (microseconds elapsed).
        Mirrors Python `Scope(label, time=True)`.
        """
        if DEBUG_LOG:
            ctx().push_scope(label, True)
        __self = Scope.__new__(Scope)
        __self.label = str(label)
        return __self

    def drop(self) -> None:
        if DEBUG_LOG:
            ctx().pop_scope()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.drop()


def debug(tmpl, args) -> None:
    """
    Append a `msg` node under the current scope. `tmpl` is a Python-style
    format-string fragment using `{name}` slots; `args` provide the values
    referenced by those slots.
    """
    if not DEBUG_LOG:
        return
    ctx().debug(tmpl, args)


def vis(name, value) -> None:
    """
    Append a vis node under the current scope, routed through the per-unit
    `Dumper` for same-elision.
    """
    if not DEBUG_LOG:
        return
    ctx().vis(name, value)


def flush() -> None:
    """
    Print the root scope as one JSON line to stdout. MUST be called from
    inside the top-level `Scope::new("turn")` block, before that block's
    guard drops.
    """
    if not DEBUG_LOG:
        return
    ctx().flush()


def dot(ct, pos, r, g, b) -> None:
    """
    Wrapper over `Controller::draw_indicator_dot`. Engine-side overlay,
    visible to all spectators, on/off globally per replay.
    """
    if not DEBUG_LOG:
        return
    ct.draw_indicator_dot(pos, r, g, b)


def line(ct, pos_a, pos_b, r, g, b) -> None:
    """Wrapper over `Controller::draw_indicator_line`."""
    if not DEBUG_LOG:
        return
    ct.draw_indicator_line(pos_a, pos_b, r, g, b)
