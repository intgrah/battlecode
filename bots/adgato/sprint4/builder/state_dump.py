from __future__ import annotations

from typing import TYPE_CHECKING


from visualiser import (
    Colour,
    F32Grid,
    I16Grid,
    Palette,
    PaletteStop,
    Tiles,
    emit,
)

if TYPE_CHECKING:
    from cambc import Controller

    from state import State
    from builder import Builder

__all__ = ["dump"]

TRANSPARENT = Colour(0, 0, 0, 0)

P_FOG = Palette(
    stops=[
        PaletteStop(0.0, Colour(0, 0, 0, 0)),
        PaletteStop(1.0, Colour(0, 0, 0, 180)),
    ],
    special={0: TRANSPARENT},
)
P_COST = Palette(
    stops=[
        PaletteStop(0.0, Colour(50, 200, 50, 140)),
        PaletteStop(1.0, Colour(200, 50, 50, 140)),
    ],
    special={-1: TRANSPARENT},
)
P_BOOL = Palette(
    stops=[
        PaletteStop(0.0, Colour(0, 0, 0, 0)),
        PaletteStop(1.0, Colour(200, 0, 0, 140)),
    ],
    special={0: TRANSPARENT},
)
P_GREEN = Palette(
    stops=[
        PaletteStop(0.0, Colour(0, 0, 0, 0)),
        PaletteStop(1.0, Colour(0, 200, 0, 160)),
    ],
    special={0: TRANSPARENT},
)
P_RED = Palette(
    stops=[
        PaletteStop(0.0, Colour(0, 0, 0, 0)),
        PaletteStop(1.0, Colour(200, 0, 0, 160)),
    ],
    special={0: TRANSPARENT},
)
P_FLOW = Palette(
    stops=[],
    special={
        0: TRANSPARENT,
        1: Colour(0, 60, 0, 60),
        2: Colour(0, 100, 0, 100),
        3: Colour(0, 160, 0, 160),
        4: Colour(0, 220, 0, 220),
    },
)
P_PASS = Palette(
    stops=[],
    special={
        0: Colour(100, 0, 0, 100),
        1: Colour(0, 100, 0, 100),
        2: Colour(100, 100, 0, 100),
    },
)

def _unpad(grid: list[int], state: State) -> list[int]:
    """Extract the real w*h interior from a padded pw*ph cost grid."""
    w, h, pad, pw = state.w, state.h, state.pad, state.pw
    out: list[int] = [0] * (w * h)
    for y in range(h):
        row_start = (y + pad) * pw + pad
        for x in range(w):
            out[y * w + x] = grid[row_start + x]
    return out


def dump(state: State, _ct: Controller) -> None:
    emit(
        unseen=F32Grid(
            [0.0 if e is not None else 1.0 for e in state.env],
            palette=P_FOG,
        ),
        cost=F32Grid(
            [c if c < 1e6 else -1 for c in _unpad(state.cost_grid, state)],
            palette=P_COST,
        ),
        conv_cost=F32Grid(
            [c if c < 1e6 else -1 for c in _unpad(state.conveyor_cost_grid, state)],
            palette=P_COST,
        ),
        enemy_launcher=Tiles(
            [(p.x, p.y) for p in state.adjacent_to_enemy_launcher],
        ),
        unconnected_harvester=Tiles(
            [(p.x, p.y) for p in state.adjacent_to_unconnected_harvester],
        ),
        harvester_adjacent=Tiles(
            [(p.x, p.y) for p in state.adjacent_to_harvester],
        )
    )
