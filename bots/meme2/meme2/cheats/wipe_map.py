"""Replace every tile's terrain with `Environment.EMPTY`.

Walls, ore tiles, anything painted on the map gets neutralised. Tile
`building` and `builder_bot` pointers are left alone — caller decides
what to do with extant entities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Environment

if TYPE_CHECKING:
    from rust import Game


def wipe_map(g: Game) -> None:
    w = g.game_map.width
    h = g.game_map.height
    for x in range(w):
        for y in range(h):
            g.game_map.tile(x, y).environment = Environment.EMPTY
