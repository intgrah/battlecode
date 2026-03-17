from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..types import Context


@dataclass
class Section:
    name: str
    deps: frozenset[str]
    analyze: Callable[[Context, list[int]], Any]
    render: Callable[[Any, list[int]], str]


SECTIONS: dict[str, Section] = {}


def register(
    name: str,
    deps: frozenset[str],
    analyze: Callable[[Context, list[int]], Any],
    render: Callable[[Any, list[int]], str],
) -> None:
    SECTIONS[name] = Section(name, deps, analyze, render)


from . import bots as _bots  # noqa: F401
from . import combat as _combat  # noqa: F401
from . import compare as _compare  # noqa: F401
from . import defense as _defense  # noqa: F401
from . import economy as _economy  # noqa: F401
from . import network as _network  # noqa: F401
from . import spatial as _spatial  # noqa: F401
from . import summary as _summary  # noqa: F401
