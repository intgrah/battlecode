"""Per-turn state dump for drewfett/v54. Adds vis nodes to the debug
tree under categorical scopes (terrain, identity, sets). Mirrors the
intgrah dump shape so the same viewer overlays work."""

from __future__ import annotations

from typing import TYPE_CHECKING

from debug import Scope, vis
from visualiser import (
    TRANSPARENT,
    Colour,
    DumpBoolGrid,
    DumpI16Grid,
    DumpScalar,
    DumpTiles,
    Palette,
    PaletteStop,
)

if TYPE_CHECKING:
    from cambc import Controller

    from .state import State

__all__ = ["dump"]

P_FOG = Palette(
    stops=[
        PaletteStop(t=False, colour=TRANSPARENT),
        PaletteStop(t=True, colour=Colour(0, 0, 0, 180)),
    ],
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
    with Scope("dump"):
        with Scope("terrain"):
            vis(
                "unseen",
                DumpBoolGrid([e is None for e in state.env], palette=P_FOG),
            )
            vis(
                "cost",
                DumpI16Grid(
                    [c if c < 1e6 else -1 for c in _unpad(state.cost_grid, state)],
                    palette=P_COST,
                ),
            )
            vis(
                "conv_cost",
                DumpI16Grid(
                    [
                        c if c < 1e6 else -1
                        for c in _unpad(state.conveyor_cost_grid, state)
                    ],
                    palette=P_COST,
                ),
            )
        with Scope("sets"):
            vis("enemy_launcher", DumpTiles(state.adjacent_to_enemy_launcher))
            vis(
                "unconnected_harvester",
                DumpTiles(state.adjacent_to_unconnected_harvester),
            )
            vis("harvester_adjacent", DumpTiles(state.adjacent_to_harvester))
        with Scope("identity"):
            vis("symmetry", DumpScalar(str(state.symmetry)))
            vis("symmetry_candidates", DumpScalar(str(state.symmetry_candidates)))
            vis("role", DumpScalar(str(state.role)))
