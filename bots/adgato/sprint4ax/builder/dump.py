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

from .flow import FLOW_AX, FLOW_RAX, FLOW_TI

if TYPE_CHECKING:
    from cambc import Controller

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


def _unpad(grid: list[int], self: Builder) -> list[int]:
    """Extract the real w*h interior from a padded pw*ph cost grid."""
    w, h, pad, pw = self.w, self.h, self.pad, self.pw
    out: list[int] = [42] * (w * h)
    for y in range(h):
        row_start = (y + pad) * pw + pad
        for x in range(w):
            out[y * w + x] = grid[row_start + x]
    return out


def _unpad1(grid: bytearray, self: Builder) -> list[int]:
    """Extract the real w*h interior from a padded pw*ph cost grid."""
    w, h, _pw = self.w, self.h, self.pw
    out: list[int] = [42] * (w * h)
    for y in range(h):
        row_start = (y + 1) * 52 + 1
        for x in range(w):
            out[y * w + x] = grid[row_start + x]
    return out


def dump(self: Builder, _ct: Controller) -> None:

    w, h, stride = self.w, self.h, self.dist_stride

    if self.dump_path:
        prev = self.dump_path[0]
        for p in self.dump_path[1:]:
            if self.sq_dist(p, prev) == 1:
                _ct.draw_indicator_line(self.pos(prev), self.pos(p), 240, 180, 0)
            else:
                _ct.draw_indicator_line(self.pos(prev), self.pos(p), 255, 120, 0)
            prev = p

    self.dump_path = None

    crnd = self.rnd
    patrol = [0.0] * (w * h)
    for i, rnd, scale in self.patrol_queue:
        pos = self.pos(i)
        patrol[pos.y * w + pos.x] = scale * (crnd - rnd)

    if self.dangling_output >= 0:
        print(self.dangling_flow)
        _ct.draw_indicator_dot(self.pos(self.dangling_output), 255, 0, 0)

    env = self.env
    flow = self.flow

    emit(
        unseen=F32Grid(
            [
                0.0 if env[y * stride + x] is not None else 1.0
                for y in range(h)
                for x in range(w)
            ],
            palette=P_FOG,
        ),
        ti_flow=I16Grid(
            [
                flow[y * stride + x].get_flow()[FLOW_TI]
                for y in range(h)
                for x in range(w)
            ],
            palette=P_FLOW,
        ),
        ax_flow=I16Grid(
            [
                flow[y * stride + x].get_flow()[FLOW_AX]
                for y in range(h)
                for x in range(w)
            ],
            palette=P_FLOW,
        ),
        rax_flow=I16Grid(
            [
                flow[y * stride + x].get_flow()[FLOW_RAX]
                for y in range(h)
                for x in range(w)
            ],
            palette=P_FLOW,
        ),
        conv_cost=F32Grid(
            [c if c < 1e6 else -1 for c in _unpad(self.conveyor_cost_grid, self)],
            palette=P_COST,
        ),
        passable=I16Grid(
            _unpad1(self.pass_grid.passable, self),
            palette=P_PASS,
        ),
        patrol=F32Grid(
            patrol,
            palette=P_RED,
        ),
        enemy_launcher=Tiles(
            [(self.pos(p).x, self.pos(p).y) for p in self.adjacent_to_enemy_launcher],
        ),
        unconnected_harvester=Tiles(
            [
                (self.pos(p).x, self.pos(p).y)
                for p in self.adjacent_to_unconnected_harvester
            ],
        ),
        harvester_adjacent=Tiles(
            [(self.pos(p).x, self.pos(p).y) for p in self.adjacent_to_harvester],
        ),
    )
