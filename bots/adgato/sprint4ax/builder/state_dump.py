from __future__ import annotations

from typing import TYPE_CHECKING

from visualiser import Grid, Palette, Scalar, Tiles, emit

from .flow import FLOW_AX, FLOW_RAX, FLOW_TI

if TYPE_CHECKING:
    from cambc import Controller

    from .state import State

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

    flows = [f.get_flow() for f in state.flow]

    crnd = _ct.get_current_round()
    patrol = [0] * len(state.env)
    for pos, rnd, scale in state.patrol_queue:
        i = pos.y * state.w + pos.x
        patrol[i] = scale * (crnd - rnd)

    emit(
        unseen=Grid(
            [0.0 if e is not None else 1.0 for e in state.env],
            palette=P_FOG,
        ),
        cost=Grid(
            [c if c < 1e6 else -1 for c in _unpad(state.cost_grid, state)],
            palette=P_COST,
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
            [c if c < 1e6 else -1 for c in _unpad(state.conveyor_cost_grid, state)],
            palette=P_COST,
        ),
        patrol=Grid(
            patrol,
            palette=P_RED,
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
    )
