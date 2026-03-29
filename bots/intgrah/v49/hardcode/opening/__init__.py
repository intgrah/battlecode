from __future__ import annotations

__all__ = ["Opening", "get_opening", "register"]

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .dsl import DslTurn

if TYPE_CHECKING:
    from hardcode.known import KnownMap


@dataclass(frozen=True, slots=True)
class Opening:
    core_spawns: list[tuple[int, int] | None]
    builder_scripts: list[list[DslTurn]]


_OPENINGS: dict[KnownMap, Opening] = {}


def get_opening(key: KnownMap) -> Opening | None:
    return _OPENINGS.get(key)


def register(key: KnownMap, opening: Opening) -> None:
    _OPENINGS[key] = opening


from .maps import arena as _arena  # noqa: E402, F401
from .maps import chemistry_class as _chemistry_class  # noqa: E402, F401
