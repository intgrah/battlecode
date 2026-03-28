from collections import deque

from building import (
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingFoundry,
    BuildingHarvester,
    BuildingSplitter,
)
from cambc import Environment, Position
from util import DELTA_TO_DIR, DIR4_DELTA

from .state import Economy, State
from .state_helpers import accepts_input_from, harvester_ore_type

__all__ = ["update_en_econ", "update_my_econ"]


def update_my_econ(state: State) -> None:
    _update_econ(
        state,
        state.my_flow,
        state.my_harvesters,
        state.my_transport,
        state.my_foundries,
        state.my_core_tiles,
    )


def update_en_econ(state: State) -> None:
    _update_econ(
        state,
        state.en_flow,
        state.en_harvesters,
        state.en_transport,
        state.en_foundries,
        state.en_core_tiles,
    )


def _update_econ(
    state: State,
    f: Economy,
    harvesters: set[Position],
    transport: set[Position],
    foundries: set[Position],
    core_tiles: set[Position],
) -> None:
    w, h = state.w, state.h
    building = state.building

    harv_idx: list[int] = [p.y * w + p.x for p in harvesters]
    trans_idx: list[int] = [p.y * w + p.x for p in transport]
    found_idx: list[int] = [p.y * w + p.x for p in foundries]
    core_idx: list[int] = [p.y * w + p.x for p in core_tiles]

    recv_idx: list[int] = trans_idx + found_idx + core_idx
    all_idx: list[int] = harv_idx + recv_idx

    n = w * h
    f_ti = f.ti
    f_ax = f.ax
    f_rax = f.rax
    f_total = f.total
    f_ti_excess = f.ti_excess
    f_ax_excess = f.ax_excess
    f_rax_excess = f.rax_excess
    f_excess = f.excess
    f_blocked = f.blocked

    in_degree = [0] * n
    out_a = [0] * n
    out_b = [0] * n
    out_c = [0] * n
    out_n = [0] * n
    is_recv = [False] * n
    in_rev_head = [-1] * n
    in_rev_next = [0] * (len(all_idx) * 4)
    in_rev_src = [0] * (len(all_idx) * 4)

    for i in all_idx:
        f_ti[i] = 0.0
        f_ax[i] = 0.0
        f_rax[i] = 0.0
        f_total[i] = 0.0
        f_ti_excess[i] = 0.0
        f_ax_excess[i] = 0.0
        f_rax_excess[i] = 0.0
        f_excess[i] = 0.0

    for i in recv_idx:
        is_recv[i] = True

    rev_ptr = 0

    def add_edge(src: int, tgt: int) -> None:
        nonlocal rev_ptr
        n_out = out_n[src]
        if n_out == 0:
            out_a[src] = tgt
        elif n_out == 1:
            out_b[src] = tgt
        elif n_out == 2:
            out_c[src] = tgt
        out_n[src] = n_out + 1
        in_degree[tgt] += 1
        in_rev_src[rev_ptr] = src
        in_rev_next[rev_ptr] = in_rev_head[tgt]
        in_rev_head[tgt] = rev_ptr
        rev_ptr += 1

    for i in trans_idx:
        bld = building[i]
        if bld is None:
            continue
        px, py = i % w, i // w
        match bld:
            case BuildingBridge(target=bt):
                if 0 <= bt.x < w and 0 <= bt.y < h:
                    tgt = bt.y * w + bt.x
                    if is_recv[tgt]:
                        add_edge(i, tgt)
            case BuildingSplitter(direction=d):
                dx, dy = d.delta()
                for odx, ody in [(dx, dy), (-dy, dx), (dy, -dx)]:
                    nx, ny = px + odx, py + ody
                    if 0 <= nx < w and 0 <= ny < h:
                        tgt = ny * w + nx
                        if is_recv[tgt]:
                            add_edge(i, tgt)
            case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
                dx, dy = d.delta()
                nx, ny = px + dx, py + dy
                if 0 <= nx < w and 0 <= ny < h:
                    tgt = ny * w + nx
                    if is_recv[tgt]:
                        add_edge(i, tgt)

    for i in found_idx:
        px, py = i % w, i // w
        for ddx, ddy in DIR4_DELTA:
            nx, ny = px + ddx, py + ddy
            if 0 <= nx < w and 0 <= ny < h:
                ni = ny * w + nx
                if is_recv[ni]:
                    from_dir = DELTA_TO_DIR.get((ddx, ddy))
                    if from_dir is not None and accepts_input_from(state, ni, from_dir):
                        add_edge(i, ni)

    queue: deque[int] = deque()
    for i in harv_idx:
        px, py = i % w, i // w
        for ddx, ddy in DIR4_DELTA:
            nx, ny = px + ddx, py + ddy
            if 0 <= nx < w and 0 <= ny < h:
                ni = ny * w + nx
                if is_recv[ni]:
                    from_dir = DELTA_TO_DIR.get((ddx, ddy))
                    if from_dir is not None and accepts_input_from(state, ni, from_dir):
                        add_edge(i, ni)
        queue.append(i)

    for i in recv_idx:
        if in_degree[i] == 0:
            queue.append(i)

    while queue:
        ci = queue.popleft()
        bld = building[ci]
        if bld is None:
            continue
        n_out = out_n[ci]

        match bld:
            case BuildingHarvester():
                ore = harvester_ore_type(state, ci)
                denom = max(n_out, 1)
                push = 0.25 / denom
                excess = 0.25 - push * n_out
                for k in range(n_out):
                    oi = out_a[ci] if k == 0 else out_b[ci] if k == 1 else out_c[ci]
                    match ore:
                        case Environment.ORE_TITANIUM:
                            f_ti[oi] += push
                        case Environment.ORE_AXIONITE:
                            f_ax[oi] += push
                    f_total[oi] += push
                    in_degree[oi] -= 1
                    if in_degree[oi] <= 0:
                        queue.append(oi)
                match ore:
                    case Environment.ORE_TITANIUM:
                        f_ti_excess[ci] = excess
                    case Environment.ORE_AXIONITE:
                        f_ax_excess[ci] = excess
                f_excess[ci] = excess
            case BuildingFoundry():
                ti_in = f_ti[ci]
                ax_in = f_ax[ci]
                refined = min(ti_in, ax_in)
                f_ti_excess[ci] = ti_in - refined
                f_ax_excess[ci] = ax_in - refined
                rax_in = f_rax[ci]
                rax_out = rax_in + refined
                push = rax_out / n_out if n_out > 0 else 0.0
                for k in range(n_out):
                    oi = out_a[ci] if k == 0 else out_b[ci] if k == 1 else out_c[ci]
                    f_rax[oi] += push
                    f_total[oi] += push
                    in_degree[oi] -= 1
                    if in_degree[oi] <= 0:
                        queue.append(oi)
                f_excess[ci] = (ti_in + ax_in + rax_in) - rax_out
            case (
                BuildingConveyor()
                | BuildingArmouredConveyor()
                | BuildingSplitter()
                | BuildingBridge()
            ):
                ti_in = f_ti[ci]
                ax_in = f_ax[ci]
                rax_in = f_rax[ci]
                divisor = 3 if isinstance(bld, BuildingSplitter) else 1
                ti_push = ti_in / divisor
                ax_push = ax_in / divisor
                rax_push = rax_in / divisor
                total_push = ti_push + ax_push + rax_push
                total_out = 0.0
                for k in range(n_out):
                    oi = out_a[ci] if k == 0 else out_b[ci] if k == 1 else out_c[ci]
                    f_ti[oi] += ti_push
                    f_ax[oi] += ax_push
                    f_rax[oi] += rax_push
                    f_total[oi] += total_push
                    total_out += total_push
                    in_degree[oi] -= 1
                    if in_degree[oi] <= 0:
                        queue.append(oi)
                incoming = ti_in + ax_in + rax_in
                f_ti_excess[ci] = ti_in - ti_push * n_out
                f_ax_excess[ci] = ax_in - ax_push * n_out
                f_rax_excess[ci] = rax_in - rax_push * n_out
                f_excess[ci] = incoming - total_out

    for i in recv_idx:
        f_blocked[i] = False
    seeds: deque[int] = deque()
    for i in recv_idx:
        if f_total[i] > 0.75:
            f_blocked[i] = True
            seeds.append(i)
    while seeds:
        bi = seeds.popleft()
        ri = in_rev_head[bi]
        while ri != -1:
            fi = in_rev_src[ri]
            if is_recv[fi] and not f_blocked[fi]:
                f_blocked[fi] = True
                seeds.append(fi)
            ri = in_rev_next[ri]
