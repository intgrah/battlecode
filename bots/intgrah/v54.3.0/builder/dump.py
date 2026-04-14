from __future__ import annotations

from typing import TYPE_CHECKING

from visualiser import Grid, Palette, Scalar, Tiles, emit

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder

__all__ = ["dump"]

TRANSPARENT = (0, 0, 0, 0)

P_FOG = Palette(
    stops=[(0.0, 0, 0, 0, 0), (1.0, 0, 0, 0, 180)],
    special={0: TRANSPARENT},
)
P_COST = Palette(
    stops=[(0.0, 50, 200, 50, 140), (1.0, 200, 50, 50, 140)],
    special={-1: TRANSPARENT},
)
P_BOOL = Palette(
    stops=[(0.0, 0, 0, 0, 0), (1.0, 200, 0, 0, 140)],
    special={0: TRANSPARENT},
)
P_GREEN = Palette(
    stops=[(0.0, 0, 0, 0, 0), (1.0, 0, 200, 0, 160)],
    special={0: TRANSPARENT},
)
P_RED = Palette(
    stops=[(0.0, 0, 0, 0, 0), (1.0, 200, 0, 0, 160)],
    special={0: TRANSPARENT},
)


def _unpad(self: Builder, grid: list[int]) -> list[int]:
    """Extract the real w*h interior from a padded pw*ph cost grid."""
    w, h, pad, pw = self.w, self.h, self.pad, self.pw
    out: list[int] = [0] * (w * h)
    for y in range(h):
        row_start = (y + pad) * pw + pad
        for x in range(w):
            out[y * w + x] = grid[row_start + x]
    return out


def dump(self: Builder, _ct: Controller) -> None:
    emit(
        unseen=Grid(
            [0.0 if e is not None else 1.0 for e in self.env],
            palette=P_FOG,
        ),
        cost=Grid(
            [c if c < 1e6 else -1 for c in _unpad(self, self.cost_grid)],
            palette=P_COST,
        ),
        conv_cost=Grid(
            [c if c < 1e6 else -1 for c in _unpad(self, self.conveyor_cost_grid)],
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
