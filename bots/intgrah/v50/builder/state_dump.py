"""Dump builder belief state using the visualiser package."""

from cambc import Controller
from visualiser import Grid, Scalar, Tiles, emit

from .state import State


def dump(state: State, ct: Controller) -> None:
    seen = [1 if e is not None else 0 for e in state.env]
    emit(
        seen=Grid(seen, palette="grey"),
        flow_ti=Grid(state.flow.ti, palette="green", null=0),
        flow_ax=Grid(state.flow.ax, palette="blue", null=0),
        flow_rax=Grid(state.flow.rax, palette="viridis", null=0),
        flow_excess=Grid(state.flow.excess, palette="red_green", null=0),
        blocked=Grid(
            [1 if b else 0 for b in state.flow.blocked], palette="red", null=0
        ),
        my_frac=Grid(state.flow.my_frac, palette="green", null=0),
        en_frac=Grid(state.flow.en_frac, palette="red", null=0),
        scale=Scalar(round(ct.get_scale_percent(), 1)),
        ore_ti=Tiles([(i % state.w, i // state.w) for i in state.ore_ti]),
        ore_ax=Tiles([(i % state.w, i // state.w) for i in state.ore_ax]),
    )
