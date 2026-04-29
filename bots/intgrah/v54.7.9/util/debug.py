"""Bot-side debug helpers — structured per-turn JSON tree + cambc
indicator overlays.

Per-turn flow:
- The first `Scope` of the turn starts a fresh root node and stack.
- Nested `Scope`s become child nodes of the current top-of-stack scope.
- Bodies append `msg` and `vis` nodes via `debug()` and `vis()`.
- At end of turn, the bot calls `flush()` which prints the root tree as
  one line of JSON to stdout.

The same-elision cache (used by `vis()` to emit `{"$type": "same"}`
when a payload is unchanged from the previous turn) is owned by a
`Dumper` instance from `util.visualiser`. The scope stack is shared
between the module-level `Scope` machinery and the Dumper (Dumper
holds a read-only reference to it).

`dot()` and `line()` wrap `ct.draw_indicator_dot` / `_line`. These are
the cambc engine-side overlay API: visible to all spectators, on/off
globally per replay.
"""

from __future__ import annotations

import json
from contextlib import AbstractContextManager
from time import perf_counter_ns
from typing import TYPE_CHECKING, Any, ClassVar, Final, Self, override

from config import DEBUG_LOG

from util.visualiser import Dump, Dumper, _auto_wrap

if TYPE_CHECKING:
    from types import TracebackType

    from cambc import Controller, Position

__all__ = ["Scope", "debug", "dot", "flush", "line", "vis"]


_TYPE = "$type"


# Active scope stack. `_stack[0]` is the per-turn root once the
# top-level `Scope("turn")` has been entered; `_stack[-1]` is the
# current parent for new children. Single-threaded per subinterpreter.
_stack: list[dict[str, Any]] = []

# Per-subinterpreter Dumper. Holds the same-elision cache and a
# read-only reference to `_stack`.
_dumper: Final[Dumper] = Dumper(_stack)


def _push(node: dict[str, Any]) -> None:
    if _stack:
        _stack[-1]["children"].append(node)
    _stack.append(node)


def _pop() -> dict[str, Any]:
    return _stack.pop()


def _emit_child(node: dict[str, Any]) -> None:
    if _stack:
        _stack[-1]["children"].append(node)


class Scope(AbstractContextManager):
    """Tree-internal node. On enter, push a `scope` node onto the stack
    and attach to its parent. On exit, record `us` if `time=True`, then
    pop. Exceptions propagate cleanly — `__exit__` always pops.
    """

    _root_t0: ClassVar[int] = 0

    def __init__(self, label: str, *, time: bool = False) -> None:
        self.label = label
        self.time = time

    if DEBUG_LOG:

        @override
        def __enter__(self) -> Self:
            node: dict[str, Any] = {
                _TYPE: "scope",
                "name": self.label,
                "children": [],
            }
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
        """Append a msg node under the current scope. `tmpl` is a Python
        format-string fragment using `{name}` slots; `args` provide the
        values referenced by those slots. Raw Python values (Position,
        int, str, bool, None) are auto-wrapped into the appropriate
        widget type (Position -> tile widget). Pre-typed `Dump*` values
        are accepted unchanged.
        """
        _emit_child(
            {
                _TYPE: "msg",
                "tmpl": tmpl,
                "args": {k: _auto_wrap(v) for k, v in args.items()},
            },
        )

    def vis(name: str, value: Dump) -> None:
        """Append a vis node under the current scope. `value` must be one
        of the `Dump*` types defined in `util.visualiser`. Same-elision
        is handled by the module-level `Dumper`.
        """
        _dumper.dump(name, value)

    _last_flush_us: int = 0

    def flush() -> None:
        """Print the root scope as one JSON line. MUST be called from
        inside the top-level `Scope("turn", ...)` block, before that
        block's `__exit__` pops the root."""
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
        pos_a: Position,
        pos_b: Position,
        r: int,
        g: int,
        b: int,
    ) -> None:
        ct.draw_indicator_line(pos_a, pos_b, r, g, b)
else:

    def debug(tmpl: str, /, **args: object) -> None:
        pass

    def vis(name: str, value: Dump) -> None:
        pass

    def flush() -> None:
        pass

    def dot(ct: Controller, pos: Position, r: int, g: int, b: int) -> None:
        pass

    def line(
        ct: Controller,
        pos_a: Position,
        pos_b: Position,
        r: int,
        g: int,
        b: int,
    ) -> None:
        pass
