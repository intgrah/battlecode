from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from builder.build import Action
    from cambc import Direction
    from hardcode.known import KnownMap


@dataclass(frozen=True, slots=True)
class Move:
    direction: Direction


@dataclass(frozen=True, slots=True)
class Build:
    action: Action


@dataclass(frozen=True, slots=True)
class Wait:
    pass


type Step = Move | Build | Wait


@dataclass(frozen=True, slots=True)
class Opening:
    core_spawns: list[tuple[int, int] | None]
    builder_scripts: list[list[Step]]


_OPENINGS: dict[KnownMap, Opening] = {}


def get_opening(key: KnownMap) -> Opening | None:
    return _OPENINGS.get(key)


def register(key: KnownMap, opening: Opening) -> None:
    _OPENINGS[key] = opening


from . import arena as _arena  # noqa: E402, F401
from . import battlebot as _battlebot  # noqa: E402, F401
