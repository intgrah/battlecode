from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from builder.build import Action
    from cambc import Direction
    from hardcode.known import KnownMap


type OpeningBuilderTurn = (
    tuple[Direction | None, Action | None] | tuple[Action | None, Direction | None]
)


@dataclass(frozen=True, slots=True)
class Opening:
    core_spawns: list[tuple[int, int] | None]
    builder_scripts: dict[int, list[OpeningBuilderTurn]]


_OPENINGS: dict[KnownMap, Opening] = {}


def get_opening(key: KnownMap) -> Opening | None:
    return _OPENINGS.get(key)


def register(key: KnownMap, opening: Opening) -> None:
    _OPENINGS[key] = opening
