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
    n = state.w * state.h
    data = {
        "w": state.w,
        "h": state.h,
        "round": ct.get_current_round(),
        "eid": ct.get_id(),
        "pos": [state.pos.x, state.pos.y],
        "explore_radius": state.explore_radius,
        "env": [
            state.env[i].value if state.env[i] is not None else None for i in range(n)
        ],
        "entity": [
            [type(state.building[i]).__name__, state.building[i].team.value]
            if state.building[i] is not None
            else None
            for i in range(n)
        ],
        "direction": [
            state.building[i].direction.value
            if state.building[i] is not None
            and isinstance(
                state.building[i],
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
            for i in range(n)
        ],
        "bridge_target": {
            str(i): [state.building[i].target[0], state.building[i].target[1]]
            for i in range(n)
            if isinstance(state.building[i], BuildingBridge)
        },
        "my_core": list(state.my_core),
        "ore_ti": list(state.ore_ti),
        "ore_ax": list(state.ore_ax),
        "my_harvesters": [[p.x, p.y] for p in state.my_harvesters],
        "my_transport": [[p.x, p.y] for p in state.my_transport],
        "my_foundries": [[p.x, p.y] for p in state.my_foundries],
        "flow_ti": {
            i: round(state.my_flow.ti[i], 3)
            for i in range(n)
            if state.my_flow.ti[i] > 0.001
        },
        "flow_ax": {
            i: round(state.my_flow.ax[i], 3)
            for i in range(n)
            if state.my_flow.ax[i] > 0.001
        },
        "flow_rax": {
            i: round(state.my_flow.rax[i], 3)
            for i in range(n)
            if state.my_flow.rax[i] > 0.001
        },
        "blocked": [i for i in range(n) if state.my_flow.blocked[i]],
        "excess_ti": {
            i: round(state.my_flow.ti_excess[i], 3)
            for i in range(n)
            if state.my_flow.ti_excess[i] > 0.001
        },
        "excess_ax": {
            i: round(state.my_flow.ax_excess[i], 3)
            for i in range(n)
            if state.my_flow.ax_excess[i] > 0.001
        },
        "excess_rax": {
            i: round(state.my_flow.rax_excess[i], 3)
            for i in range(n)
            if state.my_flow.rax_excess[i] > 0.001
        },
        "leakage": {
            i: state.leakage_mask[i]
            for i in range(n)
            if state.leakage_mask is not None and state.leakage_mask[i] != 0
        },
        "unit_tiles": [[p.x, p.y] for p in state.unit_tiles],
        "symmetry": state.symmetry.name if state.symmetry is not None else None,
    }
    print("BELIEF:" + json.dumps(data, separators=(",", ":")))
