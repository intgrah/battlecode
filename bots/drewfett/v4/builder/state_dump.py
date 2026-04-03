"""Dump builder belief state using the visualiser package."""

from building import BuildingSentinel
from cambc import Controller
from util import INF
from visualiser import Grid, Palette, Scalar, Tiles, emit

from .state import State

TRANSPARENT = (0, 0, 0, 0)

P_GREEN = Palette(
    stops=[(0.0, 0, 0, 0, 0), (1.0, 0, 200, 0, 160)], special={0: TRANSPARENT}
)
P_BLUE = Palette(
    stops=[(0.0, 0, 0, 0, 0), (1.0, 0, 0, 200, 160)], special={0: TRANSPARENT}
)
P_RED = Palette(
    stops=[(0.0, 0, 0, 0, 0), (1.0, 200, 0, 0, 160)], special={0: TRANSPARENT}
)
P_RED_GREEN = Palette(
    stops=[(0.0, 200, 0, 0, 160), (0.5, 0, 0, 0, 0), (1.0, 0, 200, 0, 160)],
    special={0: TRANSPARENT},
)
P_FOG = Palette(
    stops=[(0.0, 0, 0, 0, 0), (1.0, 0, 0, 0, 180)], special={0: TRANSPARENT}
)
P_STALENESS = Palette(
    stops=[(0.0, 0, 200, 0, 120), (1.0, 200, 0, 0, 180)],
    special={-1: TRANSPARENT},
)
P_BOOL = Palette(
    stops=[(0.0, 0, 0, 0, 0), (1.0, 200, 0, 0, 140)], special={0: TRANSPARENT}
)
P_DANGER = Palette(
    stops=[(0.0, 0, 0, 0, 0), (1.0, 255, 100, 0, 160)], special={0: TRANSPARENT}
)
P_VIRIDIS = Palette(
    stops=[(0.0, 68, 1, 84, 160), (0.5, 33, 145, 140, 160), (1.0, 253, 231, 37, 160)],
    special={0: TRANSPARENT, -1: TRANSPARENT},
)
P_COVERAGE = Palette(
    stops=[(0.0, 0, 0, 0, 0), (1.0, 0, 150, 255, 100)],
    special={0: TRANSPARENT},
)
P_APPROACH = Palette(
    stops=[(0.0, 0, 0, 0, 0), (0.05, 40, 40, 120, 80), (0.15, 100, 50, 150, 120), (0.3, 200, 80, 50, 160), (1.0, 255, 30, 30, 220)],
    special={0: TRANSPARENT},
)


def dump(state: State, ct: Controller) -> None:
    rnd = ct.get_current_round()
    n = state.w * state.h
    danger = state.danger_zones

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
        flow_ax=Grid(state.flow.ax, palette=P_BLUE),
        flow_excess=Grid(state.flow.excess, palette=P_RED_GREEN),
        blocked=Grid(
            [1 if b else 0 for b in state.flow.blocked],
            palette=P_BOOL,
        ),
        my_frac=Grid(state.flow.my_frac, palette=P_GREEN),
        en_frac=Grid(state.flow.en_frac, palette=P_RED),
        danger=Grid(
            [1 if i in danger else 0 for i in range(n)],
            palette=P_DANGER,
        ),
        en_threat=Grid(
            [float(state.en_gunner[i] + state.en_sentinel[i] + state.en_breach[i] + state.en_launcher[i]) for i in range(n)],
            palette=Palette(
                stops=[(0.0, 255, 100, 0, 120), (1.0, 255, 0, 0, 200)],
                special={0: TRANSPARENT},
            ),
        ),
        my_coverage=Grid(state.my_threat, palette=P_COVERAGE),
        en_threat_raw=Scalar(str({
            (i % state.w, i // state.w): state.en_gunner[i] + state.en_sentinel[i] + state.en_breach[i] + state.en_launcher[i]
            for i in range(n)
            if state.en_gunner[i] + state.en_sentinel[i] + state.en_breach[i] + state.en_launcher[i] > 0
        })),
        scale=Scalar(round(ct.get_scale_percent(), 1)),
        ore_ti=Tiles([(i % state.w, i // state.w) for i in state.ore_ti]),
        ore_ax=Tiles([(i % state.w, i // state.w) for i in state.ore_ax]),
        **_vulnerability_layer(state, n),
    )


def _vulnerability_layer(state: State, n: int) -> dict:
    from .task_defend_core import (
        _build_coverage,
        _ensure_approach_flow,
        _ensure_enemy_dist,
    )

    enemy_dist = _ensure_enemy_dist(state)
    if enemy_dist is None:
        empty = [0.0] * n
        return {
            "enemy_dist": Grid(empty, palette=P_VIRIDIS),
            "approach_flow": Grid(empty, palette=P_APPROACH),
            "coverage": Grid(empty, palette=P_COVERAGE),
        }

    approach = _ensure_approach_flow(state, enemy_dist)
    covered = _build_coverage(state)
    cov_grid = [1.0 if i in covered else 0.0 for i in range(n)]

    sentinel_count = sum(
        1 for ti in state.my_turrets
        if isinstance(state.building[ti], BuildingSentinel)
        and state.building[ti].team == state.my_team
    )

    return {
        "enemy_dist": Grid(
            [d if d < INF else -1 for d in enemy_dist],
            palette=P_VIRIDIS,
        ),
        "approach_flow": Grid(approach, palette=P_APPROACH),
        "coverage": Grid(cov_grid, palette=P_COVERAGE),
        "sentinels": Scalar(sentinel_count),
        "my_core": Scalar(f"({state.my_core.x},{state.my_core.y}) map={state.w}x{state.h}"),
        "en_core_pos": Scalar(f"({state.en_core_pos.x},{state.en_core_pos.y})" if state.en_core_pos else "unknown"),
        "symmetry": Scalar(state.symmetry.name if state.symmetry else f"candidates={[s.name for s in state.sym_candidates]}"),
    }
