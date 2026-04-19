from __future__ import annotations

from contextlib import AbstractContextManager
from time import perf_counter_ns
from typing import TYPE_CHECKING, ClassVar, Self, override

from config import DEBUG_TIMING

if TYPE_CHECKING:
    from types import TracebackType

__all__ = ["Timer"]


class Timer(AbstractContextManager):
    """Context manager-based timing.
    Nested contexts result in indentation.
    """

    _depth: ClassVar[int] = 0
    """Global variable representing depth. Not thread safe.
    Units run in separate subinterpreters, and multi-threading is not allowed,
    so this is fine.
    """

    t0: int
    """Start time."""
    t1: int
    """End time."""

    def __init__(self, name: str) -> None:
        self.name = name

    if DEBUG_TIMING:

        @override
        def __enter__(self) -> Self:
            Timer._depth += 1
            self.t0 = perf_counter_ns()
            return self

        @override
        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> bool | None:
            Timer._depth -= 1
            indent = "  " * Timer._depth
            self.t1 = perf_counter_ns()
            dt = self.t1 - self.t0
            print(f"{indent}{self.name}={dt // 1000}us")
    else:

        @override
        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> bool | None:
            pass
