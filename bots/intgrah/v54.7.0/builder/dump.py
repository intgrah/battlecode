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
    Scalar,
    Tiles,
    emit,
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
    w, h = self.w, self.h
    env = self.env
    cost_grid = self.cost_grid
    conveyor_cost_grid = self.conveyor_cost_grid
    bfs_dist = self.bfs_dist
    emit(
        unseen=BoolGrid(
            [
                e is None
                for y in range(h)
                for e in env[y * MAX_WIDTH : y * MAX_WIDTH + w]
            ],
            palette=P_FOG,
        ),
        cost=I16Grid(
            [
                c if c < 1e6 else -1
                for y in range(h)
                for c in cost_grid[y * MAX_WIDTH : y * MAX_WIDTH + w]
            ],
            palette=P_COST,
        ),
        conv_cost=I16Grid(
            [
                c if c < 1e6 else -1
                for y in range(h)
                for c in conveyor_cost_grid[y * MAX_WIDTH : y * MAX_WIDTH + w]
            ],
            palette=P_COST,
        ),
        dist=I16Grid(
            [
                c if c < 1e6 else -1
                for y in range(h)
                for c in bfs_dist[y * MAX_WIDTH : y * MAX_WIDTH + w]
            ],
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
