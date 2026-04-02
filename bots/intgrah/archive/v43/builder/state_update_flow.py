"""Flow computation via Kahn's topological sort. Mutates state flow arrays."""

from collections import deque

from cambc import EntityType, Environment
from util import DELTA_TO_DIR, DIR4_DELTA, TRANSPORT

from .state import FlowState, State
from .state_helpers import accepts_input_from, harvester_ore_type


def recompute_flow(state: State) -> None:
    _recompute_flow_impl(
        state,
        state.my_flow,
        state.my_harvesters,
        state.my_transport,
        state.my_foundries,
        state.my_core_tiles,
    )


def recompute_enemy_flow(state: State) -> None:
    _recompute_flow_impl(
        state,
        state.en_flow,
        state.en_harvesters,
        state.en_transport,
        state.en_foundries,
        state.en_core_tiles,
    )


def _recompute_flow_impl(
    state: State,
    f: FlowState,
    harvesters: set[int],
    transport: set[int],
    foundries: set[int],
    core_tiles: set[int],
) -> None:
    receivers = transport | foundries | core_tiles
    w, h = state.w, state.h

    for i in harvesters | receivers:
        f.ti[i] = 0.0
        f.ax[i] = 0.0
        f.rax[i] = 0.0
        f.total[i] = 0.0
        f.ti_excess[i] = 0.0
        f.ax_excess[i] = 0.0
        f.rax_excess[i] = 0.0
        f.excess[i] = 0.0

    in_degree: dict[int, int] = dict.fromkeys(receivers, 0)
    out_target: dict[int, list[int]] = {}
    in_reverse: dict[int, list[int]] = {}

    for i in transport:
        ent = state.entity[i]
        if ent is None:
            continue
        etype = ent[0]
        bt = state.bridge_target[i]
        d = state.direction[i]
        if etype == EntityType.BRIDGE and bt is not None:
            bx, by = bt
            if 0 <= bx < w and 0 <= by < h:
                tgt = by * w + bx
                if tgt in in_degree:
                    in_degree[tgt] += 1
                    out_target[i] = [tgt]
                    in_reverse.setdefault(tgt, []).append(i)
        elif etype == EntityType.SPLITTER and d is not None:
            ix, iy = i % w, i // w
            dx, dy = d.delta()
            outs: list[int] = []
            for odx, ody in [(dx, dy), (-dy, dx), (dy, -dx)]:
                nx, ny = ix + odx, iy + ody
                if 0 <= nx < w and 0 <= ny < h:
                    tgt = ny * w + nx
                    if tgt in in_degree:
                        outs.append(tgt)
                        in_degree[tgt] += 1
                        in_reverse.setdefault(tgt, []).append(i)
            if outs:
                out_target[i] = outs
        elif d is not None:
            dx, dy = d.delta()
            nx, ny = i % w + dx, i // w + dy
            if 0 <= nx < w and 0 <= ny < h:
                tgt = ny * w + nx
                if tgt in in_degree:
                    in_degree[tgt] += 1
                    out_target[i] = [tgt]
                    in_reverse.setdefault(tgt, []).append(i)

    for i in foundries:
        ix, iy = i % w, i // w
        outs: list[int] = []
        for ddx, ddy in DIR4_DELTA:
            nx, ny = ix + ddx, iy + ddy
            if 0 <= nx < w and 0 <= ny < h:
                ni = ny * w + nx
                if ni in in_degree:
                    from_dir = DELTA_TO_DIR.get((ddx, ddy))
                    if from_dir is not None and accepts_input_from(state, ni, from_dir):
                        outs.append(ni)
                        in_degree[ni] += 1
                        in_reverse.setdefault(ni, []).append(i)
        out_target[i] = outs

    queue: deque[int] = deque()
    for i in harvesters:
        ix, iy = i % w, i // w
        outs: list[int] = []
        for ddx, ddy in DIR4_DELTA:
            nx, ny = ix + ddx, iy + ddy
            if 0 <= nx < w and 0 <= ny < h:
                ni = ny * w + nx
                if ni in receivers:
                    from_dir = DELTA_TO_DIR.get((ddx, ddy))
                    if from_dir is not None and accepts_input_from(state, ni, from_dir):
                        outs.append(ni)
                        in_degree[ni] += 1
                        in_reverse.setdefault(ni, []).append(i)
        out_target[i] = outs
        queue.append(i)

    for i, deg in in_degree.items():
        if deg == 0:
            queue.append(i)

    while queue:
        ci = queue.popleft()
        ent = state.entity[ci]
        if ent is None:
            continue
        etype = ent[0]
        outs = out_target.get(ci, [])

        if etype == EntityType.HARVESTER:
            ore = harvester_ore_type(state, ci)
            n_out = max(len(outs), 1)
            push = 0.25 / n_out
            excess = 0.25 - push * len(outs)
            for oi in outs:
                if ore == Environment.ORE_TITANIUM:
                    f.ti[oi] += push
                elif ore == Environment.ORE_AXIONITE:
                    f.ax[oi] += push
                f.total[oi] += push
                in_degree[oi] -= 1
                if in_degree[oi] <= 0:
                    queue.append(oi)
            if ore == Environment.ORE_TITANIUM:
                f.ti_excess[ci] = excess
            elif ore == Environment.ORE_AXIONITE:
                f.ax_excess[ci] = excess
            f.excess[ci] = excess
        elif etype == EntityType.FOUNDRY:
            ti_in = f.ti[ci]
            ax_in = f.ax[ci]
            refined = min(ti_in, ax_in)
            f.ti_excess[ci] = ti_in - refined
            f.ax_excess[ci] = ax_in - refined
            rax_in = f.rax[ci]
            rax_out = rax_in + refined
            n_outs = len(outs)
            push = rax_out / n_outs if n_outs > 0 else 0.0
            for oi in outs:
                f.rax[oi] += push
                f.total[oi] += push
                in_degree[oi] -= 1
                if in_degree[oi] <= 0:
                    queue.append(oi)
            total_out = rax_out
            f.excess[ci] = (ti_in + ax_in + rax_in) - total_out
        elif etype in TRANSPORT:
            ti_in = f.ti[ci]
            ax_in = f.ax[ci]
            rax_in = f.rax[ci]
            divisor = 3 if etype == EntityType.SPLITTER else 1
            ti_push = ti_in / divisor
            ax_push = ax_in / divisor
            rax_push = rax_in / divisor
            total_push = ti_push + ax_push + rax_push
            total_out = 0.0
            for oi in outs:
                f.ti[oi] += ti_push
                f.ax[oi] += ax_push
                f.rax[oi] += rax_push
                f.total[oi] += total_push
                total_out += total_push
                in_degree[oi] -= 1
                if in_degree[oi] <= 0:
                    queue.append(oi)
            incoming = ti_in + ax_in + rax_in
            f.ti_excess[ci] = ti_in - ti_push * len(outs)
            f.ax_excess[ci] = ax_in - ax_push * len(outs)
            f.rax_excess[ci] = rax_in - rax_push * len(outs)
            f.excess[ci] = incoming - total_out

    for i in receivers:
        f.blocked[i] = False
    seeds: deque[int] = deque()
    for i in receivers:
        if f.total[i] > 0.75:
            f.blocked[i] = True
            seeds.append(i)
    while seeds:
        bi = seeds.popleft()
        for fi in in_reverse.get(bi, []):
            if fi in receivers and not f.blocked[fi]:
                f.blocked[fi] = True
                seeds.append(fi)
