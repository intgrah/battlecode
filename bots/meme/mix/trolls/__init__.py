from __future__ import annotations

from typing import TYPE_CHECKING

from trolls._base import Troll
from trolls.meme import Meme
from trolls.pong import Pong

if TYPE_CHECKING:
    from cambc import Controller

TROLLS: list[type[Troll]] = [
    Meme,
    Pong,
]


def select_troll(ct: Controller) -> Troll:
    h = hash((ct.get_map_width(), ct.get_map_height(), ct.get_team()))
    return TROLLS[h % len(TROLLS)]()


__all__ = [
    "TROLLS",
    "Meme",
    "Pong",
    "Troll",
    "select_troll",
]
