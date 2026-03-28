from collections.abc import Callable

from .known import KnownMap

DATA: dict[KnownMap, Callable[[], bytes]]
