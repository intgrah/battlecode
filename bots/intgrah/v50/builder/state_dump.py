"""Serialize builder belief state to stdout for the belief viewer."""

import json

from building import (
    BuildingArmouredConveyor,
    BuildingBreach,
    BuildingBridge,
    BuildingConveyor,
    BuildingGunner,
    BuildingSentinel,
    BuildingSplitter,
)
from cambc import Controller

from .state import State


def dump(state: State, ct: Controller) -> None:
    data = {
        "w": state.w,
        "h": state.h,
        "round": ct.get_current_round(),
        "eid": ct.get_id(),
        "pos": [state.pos.x, state.pos.y],
        "explore_radius": state.explore_radius,
        "env": [env.value if env is not None else None for env in state.env],
        "entity": [
            [type(bld).__name__, bld.team.value] if bld is not None else None
            for bld in state.building
        ],
        "direction": [
            bld.direction.value
            if bld is not None
            and isinstance(
                bld,
                (
                    BuildingConveyor,
                    BuildingArmouredConveyor,
                    BuildingSplitter,
                    BuildingGunner,
                    BuildingSentinel,
                    BuildingBreach,
                ),
            )
            else None
            for bld in state.building
        ],
        "bridge_target": {
            str(i): [bld.target[0], bld.target[1]]
            for i, bld in enumerate(state.building)
            if isinstance(bld, BuildingBridge)
        },
        "my_core": list(state.my_core),
        "ore_ti": list(state.ore_ti),
        "ore_ax": list(state.ore_ax),
        "my_harvesters": [[i % state.w, i // state.w] for i in state.my_harvesters],
        "my_transport": [[i % state.w, i // state.w] for i in state.my_transport],
        "my_foundries": [[i % state.w, i // state.w] for i in state.my_foundries],
        "flow_ti": {i: round(v, 3) for i, v in enumerate(state.flow.ti) if v > 0.001},
        "flow_ax": {i: round(v, 3) for i, v in enumerate(state.flow.ax) if v > 0.001},
        "flow_rax": {i: round(v, 3) for i, v in enumerate(state.flow.rax) if v > 0.001},
        "blocked": [i for i, b in enumerate(state.flow.blocked) if b],
        "excess_ti": {
            i: round(v, 3) for i, v in enumerate(state.flow.ti_excess) if v > 0.001
        },
        "excess_ax": {
            i: round(v, 3) for i, v in enumerate(state.flow.ax_excess) if v > 0.001
        },
        "excess_rax": {
            i: round(v, 3) for i, v in enumerate(state.flow.rax_excess) if v > 0.001
        },
        "my_frac": {
            i: round(v, 3) for i, v in enumerate(state.flow.my_frac) if v > 0.001
        },
        "en_frac": {
            i: round(v, 3) for i, v in enumerate(state.flow.en_frac) if v > 0.001
        },
        "my_total": {
            i: round(v, 3) for i, v in enumerate(state.flow.my_total) if v > 0.001
        },
        "en_total": {
            i: round(v, 3) for i, v in enumerate(state.flow.en_total) if v > 0.001
        },
        "leakage": {i: v for i, v in enumerate(state.leakage_mask or []) if v != 0},
        "unit_tiles": [[p.x, p.y] for p in state.unit_tiles],
        "symmetry": state.symmetry.name if state.symmetry is not None else None,
    }
    print("BELIEF:" + json.dumps(data, separators=(",", ":")))
