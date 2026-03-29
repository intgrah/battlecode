from __future__ import annotations

__all__ = ["Opening", "get_opening", "register"]

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hardcode.known import KnownMap

    from .dsl import DslTurn


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
from .maps import battlebot as _battlebot  # noqa: E402, F401
from .maps import chemistry_class as _chemistry_class  # noqa: E402, F401
from .maps import cinnamon_roll as _cinnamon_roll  # noqa: E402, F401
from .maps import default_large1 as _default_large1  # noqa: E402, F401
from .maps import default_small1 as _default_small1  # noqa: E402, F401
from .maps import dna as _dna  # noqa: E402, F401
from .maps import galaxy as _galaxy  # noqa: E402, F401
from .maps import landscape as _landscape  # noqa: E402, F401
from .maps import pls_buy_cucats_merch as _pls_buy_cucats_merch  # noqa: E402, F401
from .maps import tree_of_life as _tree_of_life  # noqa: E402, F401
