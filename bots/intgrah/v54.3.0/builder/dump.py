from __future__ import annotations

from typing import TYPE_CHECKING

from util import INF
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

    from builder import Builder

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
P_DIST = Palette(
    stops=[
        PaletteStop(0, Colour(50, 200, 50, 140)),
        PaletteStop(50, Colour(200, 50, 50, 140)),
    ],
    special={INF: TRANSPARENT},
)


def dump(self: Builder, _ct: Controller) -> None:
    emit(
        unseen=BoolGrid(
            [e is None for e in self.env],
            palette=P_FOG,
        ),
        cost=I16Grid(
            [c if c < 1e6 else -1 for c in self.cost_grid],
            palette=P_COST,
        ),
        conv_cost=I16Grid(
            [c if c < 1e6 else -1 for c in self.conveyor_cost_grid],
            palette=P_COST,
        ),
        dist=I16Grid(
            [c if c < 1e6 else -1 for c in self.bfs_dist],
            palette=P_COST,
        ),
        enemy_launcher=Tiles(
            [(p.x, p.y) for p in self.adjacent_to_enemy_launcher],
        ),
        unconnected_harvester=Tiles(
            [(p.x, p.y) for p in self.adjacent_to_unconnected_harvester],
        ),
        harvester_adjacent=Tiles(
            [(p.x, p.y) for p in self.adjacent_to_harvester],
        ),
        symmetry=Scalar(str(self.symmetry)),
        symmetry_candidates=Scalar(str(self.symmetry_candidates)),
        role=Scalar(str(self.role)),
    )
