"""Debug logging + scoped indentation + scoped timing.

- `debug(msg)`: indented `print`; no-op unless `DEBUG_LOG` is set.
- `Scope(label)`: context manager that announces `label` on enter, indents
  the body, no exit summary.
- `Scope(label, time=True)`: enters silently, exits with `label=Xus`.
  Replaces the old `Timer` class. Shares the same depth counter as bare
  Scope, so arbitrary nesting of timed/untimed scopes composes cleanly.
- `dot`, `line`: replay-indicator helpers.

All calls compile to no-ops when `DEBUG_LOG` is unset.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from time import perf_counter_ns
from typing import TYPE_CHECKING, ClassVar, Self, override

from config import DEBUG_LOG

if TYPE_CHECKING:
    from types import TracebackType

    from cambc import Controller, Position

__all__ = ["Scope", "debug", "dot", "line"]


class Scope(AbstractContextManager):
    """Indented, labelled block. Always announces `label` on enter. If
    `time=True`, also emits `label=Xus` on exit. Body indents one level
    deeper either way."""

    _depth: ClassVar[int] = 0
    """Shared indent depth across all Scope instances. Single-threaded per
    subinterpreter, so no lock needed."""

    def __init__(self, label: str, *, time: bool = False) -> None:
        self.label = label
        self.time = time

    if DEBUG_LOG:

        @override
        def __enter__(self) -> Self:
            print(f"{'  ' * Scope._depth}{self.label}")
            Scope._depth += 1
            if self.time:
                self._t0 = perf_counter_ns()
            return self

        @override
        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> bool | None:
            Scope._depth -= 1
            if self.time:
                self._t1 = perf_counter_ns()
                dt = (self._t1 - self._t0) // 1000
                print(f"{'  ' * Scope._depth}{self.label}={dt}us")
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

    def debug(msg: str) -> None:
        print(f"{'  ' * Scope._depth}{msg}")

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

    def debug(msg: str) -> None:
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
