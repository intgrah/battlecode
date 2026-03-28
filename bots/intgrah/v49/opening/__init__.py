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
from . import chemistry_class as _chemistry_class  # noqa: E402, F401
from . import cinnamon_roll as _cinnamon_roll  # noqa: E402, F401
from . import corridors as _corridors  # noqa: E402, F401
from . import default_large1 as _default_large1  # noqa: E402, F401
from . import default_large2 as _default_large2  # noqa: E402, F401
from . import default_medium1 as _default_medium1  # noqa: E402, F401
from . import default_medium2 as _default_medium2  # noqa: E402, F401
from . import default_small1 as _default_small1  # noqa: E402, F401
from . import default_small2 as _default_small2  # noqa: E402, F401
from . import dna as _dna  # noqa: E402, F401
from . import face as _face  # noqa: E402, F401
from . import galaxy as _galaxy  # noqa: E402, F401
from . import hooks as _hooks  # noqa: E402, F401
from . import hourglass as _hourglass  # noqa: E402, F401
from . import landscape as _landscape  # noqa: E402, F401
from . import minimaze as _minimaze  # noqa: E402, F401
from . import pls_buy_cucats_merch as _pls_buy_cucats_merch  # noqa: E402, F401
from . import shish_kebab as _shish_kebab  # noqa: E402, F401
from . import thread_of_connection as _thread_of_connection  # noqa: E402, F401
