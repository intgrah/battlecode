"""Dump builder belief state using the visualiser package."""

from cambc import Controller
from util import INF
from visualiser import Grid, Palette, Scalar, Tiles, emit

from .state import State

__all__ = ["dump"]

TRANSPARENT = (0, 0, 0, 0)
BLACK = (0, 0, 0, 180)
GREY = (80, 80, 80, 100)

P_GREEN = Palette(
    stops=[(0.0, 0, 0, 0, 0), (1.0, 0, 200, 0, 160)], special={0: TRANSPARENT}
)
P_BLUE = Palette(
    stops=[(0.0, 0, 0, 0, 0), (1.0, 0, 0, 200, 160)], special={0: TRANSPARENT}
)
P_RED = Palette(
    stops=[(0.0, 0, 0, 0, 0), (1.0, 200, 0, 0, 160)], special={0: TRANSPARENT}
)
P_VIRIDIS = Palette(
    stops=[(0.0, 68, 1, 84, 160), (0.5, 33, 145, 140, 160), (1.0, 253, 231, 37, 160)],
    special={0: TRANSPARENT},
)
P_FOG = Palette(
    stops=[(0.0, 0, 0, 0, 0), (1.0, 0, 0, 0, 180)], special={0: TRANSPARENT}
)
P_DIST = Palette(
    stops=[(0.0, 50, 200, 50, 140), (1.0, 200, 50, 50, 140)],
    special={-1: TRANSPARENT, INF: TRANSPARENT},
)
P_HEURISTIC = Palette(
    stops=[(0.0, 50, 50, 200, 140), (1.0, 200, 50, 200, 140)],
    special={-1: TRANSPARENT},
)
P_STALENESS = Palette(
    stops=[(0.0, 0, 200, 0, 120), (1.0, 200, 0, 0, 180)],
    special={-1: TRANSPARENT},
)
P_RED_GREEN = Palette(
    stops=[(0.0, 200, 0, 0, 160), (0.5, 0, 0, 0, 0), (1.0, 0, 200, 0, 160)],
    special={0: TRANSPARENT},
)
P_BOOL = Palette(
    stops=[(0.0, 0, 0, 0, 0), (1.0, 200, 0, 0, 140)], special={0: TRANSPARENT}
)
P_THREAT_GUNNER = Palette(
    stops=[(0.0, 255, 165, 0, 80), (1.0, 255, 165, 0, 180)], special={0: TRANSPARENT}
)
P_THREAT_SENTINEL = Palette(
    stops=[(0.0, 100, 100, 255, 80), (1.0, 100, 100, 255, 180)],
    special={0: TRANSPARENT},
)
P_THREAT_BREACH = Palette(
    stops=[(0.0, 255, 0, 0, 80), (1.0, 255, 0, 0, 200)], special={0: TRANSPARENT}
)
P_THREAT_LAUNCHER = Palette(
    stops=[(0.0, 255, 0, 255, 80), (1.0, 255, 0, 255, 180)], special={0: TRANSPARENT}
)


def dump(state: State, ct: Controller) -> None:
    rnd = ct.get_current_round()
    emit(
        unseen=Grid(
            [0.0 if e is not None else 1.0 for e in state.env],
            palette=P_FOG,
        ),
        staleness=Grid(
            [rnd - t if t > 0 else -1 for t in state.last_seen],
            palette=P_STALENESS,
        ),
        infra_max_staleness=Scalar(state.infra_max_staleness),
        flow_ti=Grid(state.flow.ti, palette=P_GREEN),
        flow_ax=Grid(state.flow.ax, palette=P_BLUE),
        flow_rax=Grid(state.flow.rax, palette=P_VIRIDIS),
        flow_excess=Grid(state.flow.excess, palette=P_RED_GREEN),
        blocked=Grid(
            [bool(b) for b in state.flow.blocked],
            palette=P_BOOL,
        ),
        my_frac=Grid(state.flow.my_frac, palette=P_GREEN),
        en_frac=Grid(state.flow.en_frac, palette=P_RED),
        scale=Scalar(round(ct.get_scale_percent(), 1)),
        ore_ti=Tiles([(i % state.w, i // state.w) for i in state.ore_ti]),
        ore_ax=Tiles([(i % state.w, i // state.w) for i in state.ore_ax]),
        unit_tiles=Tiles(state.unit_tiles),
        symmetry=Scalar(str(state.symmetry)),
        symmetry_candidates=Scalar(str(state.symmetry_candidates)),
        en_gunner=Grid(state.en_gunner, palette=P_THREAT_GUNNER),
        en_sentinel=Grid(state.en_sentinel, palette=P_THREAT_SENTINEL),
        en_breach=Grid(state.en_breach, palette=P_THREAT_BREACH),
        en_launcher=Grid(state.en_launcher, palette=P_THREAT_LAUNCHER),
        my_turrets=Tiles([(i % state.w, i // state.w) for i in state.my_turrets]),
        en_turrets=Tiles([(i % state.w, i // state.w) for i in state.en_turrets]),
    )
