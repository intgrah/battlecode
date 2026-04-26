from __future__ import annotations

from typing import TYPE_CHECKING

from util.constants import INF, MAX_WIDTH
from visualiser import (
    TRANSPARENT,
    BoolGrid,
    Colour,
    I16Grid,
    Palette,
    PaletteStop,
    Tiles,
)

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder

__all__ = ["dump"]

P_FOG = Palette(
    stops=[
        PaletteStop(t=False, colour=TRANSPARENT),
        PaletteStop(t=True, colour=Colour(0, 0, 0, 180)),
    ],
)
P_COST = Palette(
    stops=[
        PaletteStop(t=0, colour=Colour(50, 200, 50, 140)),
        PaletteStop(t=100, colour=Colour(200, 50, 50, 140)),
    ],
    special={-1: TRANSPARENT},
)
P_DIST = Palette(
    stops=[
        PaletteStop(t=0, colour=Colour(50, 240, 50, 140)),
        PaletteStop(t=36, colour=Colour(240, 50, 50, 140)),
    ],
    special={INF: TRANSPARENT},
)


def dump(self: Builder, _ct: Controller) -> None:
    return
