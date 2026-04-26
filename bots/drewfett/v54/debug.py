"""Structured tree-shaped debug logging.

Per-turn flow:
- The first `Scope` of the turn starts a fresh root node and stack.
- Nested `Scope`s become child nodes of the current top-of-stack scope.
  Bodies append `msg` and `vis` nodes via `debug()` and `vis()`.
- At end of turn, the bot calls `flush()` which prints the root tree as
  one line of JSON to stdout. No prefix — every line of bot stdout is
  this tree.

No crash safety: if a turn raises mid-way, `flush()` is never called
and the partial tree is discarded. The validator forbids `try/finally`
so this is intentional.

Schema: see `Schema` section below. All nodes carry `$type`. Typed
values (positions, directions, etc.) are also tagged with `$type` so
the viewer can render them as hoverable widgets.

When `DEBUG_LOG` is unset, every public function is a no-op.
"""

from __future__ import annotations

import json
from contextlib import AbstractContextManager
from enum import Enum
from time import perf_counter_ns
from typing import TYPE_CHECKING, Any, ClassVar, Self, override

from config import DEBUG_LOG

if TYPE_CHECKING:
    from collections.abc import Iterable
    from types import TracebackType

    from cambc import Controller, Position

__all__ = [
    "Scope",
    "debug",
    "dot",
    "flush",
    "line",
    "tagged",
    "vis",
]


_TYPE = "$type"


if TYPE_CHECKING:
    Node = dict[str, Any]


# Active scope stack. `_stack[0]` is the per-turn root once the
# top-level `Scope("turn")` has been entered; `_stack[-1]` is the
# current parent for new children. `flush()` is called from inside
# the root scope, so it reads `_stack[0]` directly.
_stack: list[Node] = []


def _push(node: Node) -> None:
    if _stack:
        _stack[-1]["children"].append(node)
    _stack.append(node)


def _pop() -> Node:
    return _stack.pop()


def _emit_child(node: Node) -> None:
    if _stack:
        _stack[-1]["children"].append(node)


def tagged(value: object) -> Node:
    from cambc import Position  # noqa: PLC0415
    from visualiser import (  # noqa: PLC0415
        BoolGrid,
        F32Grid,
        I16Grid,
        Tiles,
        U8Grid,
        U16Grid,
        VectorField,
        serialize,
    )

    if value is None:
        return {_TYPE: "scalar", "v": None}
    if isinstance(value, bool):
        return {_TYPE: "scalar", "v": value}
    if isinstance(value, int):
        return {_TYPE: "scalar", "v": value}
    if isinstance(value, float):
        return {_TYPE: "scalar", "v": value}
    if isinstance(value, str):
        return {_TYPE: "scalar", "v": value}
    if isinstance(value, Position):
        return {_TYPE: "pos", "x": value.x, "y": value.y}
    if isinstance(value, Enum):
        return {_TYPE: "scalar", "v": value.name}
    if isinstance(
        value,
        BoolGrid | U8Grid | I16Grid | U16Grid | F32Grid | Tiles | VectorField,
    ):
        return serialize(value)
    if isinstance(value, (set, frozenset, list, tuple)):
        items = list(value)
        if items and all(isinstance(p, Position) for p in items):
            return {_TYPE: "set_pos", "v": [[p.x, p.y] for p in items]}
        return {_TYPE: "scalar", "v": [tagged(x) for x in items]}
    if isinstance(value, dict):
        return {_TYPE: "scalar", "v": {str(k): tagged(v) for k, v in value.items()}}
    return {_TYPE: "repr", "v": str(value)}


class Scope(AbstractContextManager):
    """Tree-internal node. On enter, push a `scope` node onto the stack
    and attach to its parent. On exit, record `us` if `time=True`, then
    pop."""

    _root_t0: ClassVar[int] = 0

    def __init__(self, label: str, *, time: bool = False) -> None:
        self.label = label
        self.time = time

    if DEBUG_LOG:

        @override
        def __enter__(self) -> Self:
            node: Node = {_TYPE: "scope", "name": self.label, "children": []}
            if self.time:
                node["_t0"] = perf_counter_ns()
            _push(node)
            return self

        @override
        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> bool | None:
            node = _pop()
            t0 = node.pop("_t0", None)
            if t0 is not None:
                node["us"] = (perf_counter_ns() - t0) // 1000
            return None
    else:

        @override
        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> bool | None:
            return None


if DEBUG_LOG:

    def debug(tmpl: str, /, **args: object) -> None:
        _emit_child(
            {
                _TYPE: "msg",
                "tmpl": tmpl,
                "args": {k: tagged(v) for k, v in args.items()},
            },
        )

    _vis_cache: dict[str, object] = {}

    def vis(name: str, value: object) -> None:
        payload = value if isinstance(value, dict) and _TYPE in value else tagged(value)
        if _vis_cache.get(name) == payload:
            payload = {_TYPE: "same"}
        else:
            _vis_cache[name] = payload
        _emit_child({_TYPE: "vis", "name": name, "value": payload})

    _last_flush_us: int = 0

    def flush() -> None:
        global _last_flush_us  # noqa: PLW0603
        if not _stack:
            msg = "flush() called outside any Scope"
            raise RuntimeError(msg)
        root = _stack[0]
        root["prev_flush_us"] = _last_flush_us
        t0 = perf_counter_ns()
        payload = json.dumps(root, separators=(",", ":"))
        print(payload)
        _last_flush_us = (perf_counter_ns() - t0) // 1000

    def dot(ct: Controller, pos: Position, r: int, g: int, b: int) -> None:
        ct.draw_indicator_dot(pos, r, g, b)

    def line(
        ct: Controller,
        a: Position,
        b: Position,
        r: int,
        g: int,
        bl: int,
    ) -> None:
        ct.draw_indicator_line(a, b, r, g, bl)
else:

    def debug(tmpl: str, /, **args: object) -> None:
        pass

    def vis(name: str, value: object) -> None:
        pass

    def flush() -> None:
        pass

    def dot(ct: Controller, pos: Position, r: int, g: int, b: int) -> None:
        pass

    def line(
        ct: Controller,
        a: Position,
        b: Position,
        r: int,
        g: int,
        bl: int,
    ) -> None:
        pass


def vis_grid(
    dtype: str,
    data: Iterable[bool | int | float],
    palette: str = "default",
) -> Node:
    return {_TYPE: f"{dtype}grid", "v": list(data), "palette": palette}


def vis_tiles(positions: Iterable[Position]) -> Node:
    return {_TYPE: "tiles", "v": [[p.x, p.y] for p in positions]}


def vis_same() -> Node:
    return {_TYPE: "same"}
