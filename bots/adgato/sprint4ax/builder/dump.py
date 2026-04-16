from __future__ import annotations

from typing import TYPE_CHECKING

from visualiser import Grid, Palette, Scalar, Tiles, emit

from .flow import FLOW_AX, FLOW_RAX, FLOW_TI

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
P_FLOW = Palette(
    stops=[],
    special={
        0: TRANSPARENT,
        1: (0, 60, 0, 60),
        2: (0, 100, 0, 100),
        3: (0, 160, 0, 160),
        4: (0, 220, 0, 220),
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


def dump(self: Builder, _ct: Controller) -> None:

    flows = [f.get_flow() for f in self.flow]

    if self.dump_path:
        prev = self.dump_path[0]
        for p in self.dump_path[1:]:
            if p.distance_squared(prev) == 1:
                _ct.draw_indicator_line(prev, p, 240, 180, 0)
            else:
                _ct.draw_indicator_line(prev, p, 255, 120, 0)
            prev = p

    self.dump_path = None

    crnd = self.rnd
    patrol = [0] * len(self.env)
    for pos, rnd, scale in self.patrol_queue:
        i = pos.y * self.w + pos.x
        patrol[i] = scale * (crnd - rnd)
    
    if self.dangling_output:
        print(self.dangling_flow)
        _ct.draw_indicator_dot(self.dangling_output, 255, 0, 0)

    emit(
        unseen=Grid(
            [0.0 if e is not None else 1.0 for e in self.env],
            palette=P_FOG,
        ),
        ti_flow=Grid(
            [f[FLOW_TI] for f in flows],
            palette=P_FLOW,
        ),
        ax_flow=Grid(
            [f[FLOW_AX] for f in flows],
            palette=P_FLOW,
        ),
        rax_flow=Grid(
            [f[FLOW_RAX] for f in flows],
            palette=P_FLOW,
        ),
        conv_cost=Grid(
            [c if c < 1e6 else -1 for c in _unpad(self.conveyor_cost_grid, self)],
            palette=P_COST,
        ),
        patrol=Grid(
            patrol,
            palette=P_RED,
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
    )
