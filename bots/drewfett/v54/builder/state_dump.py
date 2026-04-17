from __future__ import annotations

from typing import TYPE_CHECKING

from visualiser import (
    TRANSPARENT,
    BoolGrid,
    Colour,
    I16Grid,
    Palette,
    PaletteStop,
    Scalar,
    Tiles,
    emit,
)

if TYPE_CHECKING:
    from cambc import Controller

    from .state import State

__all__ = ["dump"]

P_FOG = Palette(
    stops=[PaletteStop(False, TRANSPARENT), PaletteStop(True, Colour(0, 0, 0, 180))],
)
P_COST = Palette(
    stops=[
        PaletteStop(0, Colour(50, 200, 50, 140)),
        PaletteStop(100, Colour(200, 50, 50, 140)),
    ],
    special={-1: TRANSPARENT},
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
        unseen=BoolGrid(
            [e is None for e in state.env],
            palette=P_FOG,
        ),
        cost=I16Grid(
            [c if c < 1e6 else -1 for c in _unpad(state.cost_grid, state)],
            palette=P_COST,
        ),
        conv_cost=I16Grid(
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
        ),
        symmetry=Scalar(str(state.symmetry)),
        symmetry_candidates=Scalar(str(state.symmetry_candidates)),
        role=Scalar(str(state.role)),
    )
