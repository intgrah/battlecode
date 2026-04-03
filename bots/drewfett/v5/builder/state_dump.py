"""Dump builder belief state using the visualiser package."""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    from visualiser import Grid, Palette, Scalar, Tiles, emit
except ImportError:
    emit = None

if TYPE_CHECKING:
    from cambc import Controller

    from .state import State

__all__ = ["dump"]


def dump(state: State, ct: Controller) -> None:
    if emit is None:
        return

    TRANSPARENT = (0, 0, 0, 0)

    P_GREEN = Palette(
        stops=[(0.0, 0, 0, 0, 0), (1.0, 0, 200, 0, 160)], special={0: TRANSPARENT}
    )
    P_RED = Palette(
        stops=[(0.0, 0, 0, 0, 0), (1.0, 200, 0, 0, 160)], special={0: TRANSPARENT}
    )
    P_FOG = Palette(
        stops=[(0.0, 0, 0, 0, 0), (1.0, 0, 0, 0, 180)], special={0: TRANSPARENT}
    )
    P_RED_GREEN = Palette(
        stops=[(0.0, 200, 0, 0, 160), (0.5, 0, 0, 0, 0), (1.0, 0, 200, 0, 160)],
        special={0: TRANSPARENT},
    )
    P_BOOL = Palette(
        stops=[(0.0, 0, 0, 0, 0), (1.0, 200, 0, 0, 140)], special={0: TRANSPARENT}
    )
    P_STALENESS = Palette(
        stops=[(0.0, 0, 200, 0, 120), (1.0, 200, 0, 0, 180)], special={-1: TRANSPARENT}
    )

    rnd = ct.get_current_round()
    w = state.w

    emit(
        unseen=Grid(
            [0.0 if e is not None else 1.0 for e in state.env],
            palette=P_FOG,
        ),
        staleness=Grid(
            [rnd - t if t > 0 else -1 for t in state.last_seen],
            palette=P_STALENESS,
        ),
        flow_ti=Grid(state.flow.ti, palette=P_GREEN),
        flow_excess=Grid(state.flow.excess, palette=P_RED_GREEN),
        blocked=Grid(
            [bool(b) for b in state.flow.blocked],
            palette=P_BOOL,
        ),
        my_frac=Grid(state.flow.my_frac, palette=P_GREEN),
        en_frac=Grid(state.flow.en_frac, palette=P_RED),
        danger=Grid(
            [1.0 if i in state.danger_zones else 0.0 for i in range(w * state.h)],
            palette=P_BOOL,
        ),
        scale=Scalar(round(ct.get_scale_percent(), 1)),
        ore_ti=Tiles([(i % w, i // w) for i in state.ore_ti]),
        unit_tiles=Tiles(state.unit_tiles),
        symmetry=Scalar(str(state.symmetry)),
        my_turrets=Tiles([(i % w, i // w) for i in state.my_turrets]),
        en_turrets=Tiles([(i % w, i // w) for i in state.en_turrets]),
        blocked_ore=Tiles([(i % w, i // w) for i in state.blocked_ore]),
    )
