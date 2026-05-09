from __future__ import annotations

from typing import TYPE_CHECKING

from trolls._base import Troll
from trolls.immune import Immune
from trolls.instant_resign import InstantResign
from trolls.pong import Pong
from trolls.silenced import Silenced
from trolls.solipsism import Solipsism

if TYPE_CHECKING:
    from cambc import Controller

TROLLS: list[type[Troll]] = [
    Pong,
]


def select_troll(ct: Controller) -> Troll:
    h = hash((ct.get_map_width(), ct.get_map_height(), ct.get_team()))
    return TROLLS[h % len(TROLLS)]()


__all__ = [
    "TROLLS",
    "Immune",
    "InstantResign",
    "Pong",
    "Silenced",
    "Solipsism",
    "Troll",
    "select_troll",
]
