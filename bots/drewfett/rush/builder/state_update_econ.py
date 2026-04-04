import time
from collections import deque
from itertools import chain

from building import (
    BuildingArmouredConveyor,
    BuildingBreach,
    BuildingBridge,
    BuildingConveyor,
    BuildingCore,
    BuildingFoundry,
    BuildingGunner,
    BuildingHarvester,
    BuildingLauncher,
    BuildingSentinel,
    BuildingSplitter,
)
from cambc import Environment
from util import DELTA_TO_DIR, DIR4_DELTA

from .state import State
from .state_helpers import accepts_input_from, harvester_ore_type

__all__ = ["update_flow"]


def update_flow(state: State) -> None:
    """
    Uhh we treat all transport buildings as equal, so we compute flow as a unified property of the whole map, and then assign attribution to certain flow
    This probably helps somewhat
    E.g. if there's an enemy harvester that you're appropriating as your own, then this algorithm will not mind (before, we computed flow separately for allied and enemy transport)
    E.g. if there's a friendly harvester that's being hijacked with four enemy sentinels, this algorithm can correctly identify that it needs to be destroyed (despite being ours) which is good

    This is toposort to find source nodes and then you compute flow in a really obvious way
    """
    _t = time.perf_counter

    _t0 = _t()
    w, h = state.w, state.h
    building = state.building
    my_team = state.my_team
    f = state.flow

    harv_idx = list(state.harvesters)
    trans_idx = list(state.transport)
    found_idx = list(state.foundries)
    turret_idx = list(state.turrets)
    core_idx = list(state.my_core_tiles | state.en_core_tiles)

    f_ti = f.ti
    f_ax = f.ax
    f_rax = f.rax
    f_total = f.total
    f_my_frac = f.my_frac
    f_en_frac = f.en_frac
    f_my_total = f.my_total
    f_en_total = f.en_total
    f_ti_excess = f.ti_excess
    f_ax_excess = f.ax_excess
    f_rax_excess = f.rax_excess
    f_excess = f.excess
    f_blocked = f.blocked

    _recv = (trans_idx, found_idx, turret_idx, core_idx)
    _all = (harv_idx, *_recv)

    in_degree = f._in_degree
    out_edges = f._out_edges
    is_recv = f._is_recv
    in_rev_head = f._in_rev_head
    in_rev_next = f._in_rev_next
    in_rev_src = f._in_rev_src
    edge_push = f._edge_push

    for i in chain(*f._prev_all):
        f_ti[i] = 0.0
        f_ax[i] = 0.0
        f_rax[i] = 0.0
        f_total[i] = 0.0
        f_my_frac[i] = 0.0
        f_en_frac[i] = 0.0
        f_my_total[i] = 0.0
        f_en_total[i] = 0.0
        f_ti_excess[i] = 0.0
        f_ax_excess[i] = 0.0
        f_rax_excess[i] = 0.0
        f_excess[i] = 0.0
        in_degree[i] = 0
        out_edges[i].clear()
        in_rev_head[i] = -1
    for i in chain(*f._prev_recv):
        is_recv[i] = False
        f_blocked[i] = False

    for i in chain(*_recv):
        is_recv[i] = True

    f._prev_all = _all
    f._prev_recv = _recv

    _t1 = _t()

    rev_ptr = 0

    def add_edge(src: int, tgt: int) -> None:
        nonlocal rev_ptr
        eidx = rev_ptr
        out_edges[src].append((tgt, eidx))
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
                        # Bridges deliver directly — no facing restriction
                        add_edge(i, tgt)
            case BuildingSplitter(direction=d):
                dx, dy = d.delta()
                for odx, ody in [(dx, dy), (-dy, dx), (dy, -dx)]:
                    nx, ny = px + odx, py + ody
                    if 0 <= nx < w and 0 <= ny < h:
                        tgt = ny * w + nx
                        if is_recv[tgt]:
                            from_dir = DELTA_TO_DIR.get((odx, ody))
                            if from_dir is not None and accepts_input_from(
                                state, tgt, from_dir
                            ):
                                add_edge(i, tgt)
            case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
                dx, dy = d.delta()
                nx, ny = px + dx, py + dy
                if 0 <= nx < w and 0 <= ny < h:
                    tgt = ny * w + nx
                    if is_recv[tgt]:
                        from_dir = DELTA_TO_DIR.get((dx, dy))
                        if from_dir is not None and accepts_input_from(
                            state, tgt, from_dir
                        ):
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

    for i in chain(*_recv):
        if in_degree[i] == 0:
            queue.append(i)

    _t2 = _t()
    topo_order: list[int] = []

    while queue:
        ci = queue.popleft()
        bld = building[ci]
        if bld is None:
            continue
        topo_order.append(ci)
        edges_ci = out_edges[ci]
        no = len(edges_ci)

        match bld:
            case BuildingHarvester():
                ore = harvester_ore_type(state, ci)
                denom = max(no, 1)
                push = 0.25 / denom
                excess = 0.25 - push * no
                for oi, eidx in edges_ci:
                    edge_push[eidx] = push
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
                push = rax_out / no if no > 0 else 0.0
                for oi, eidx in edges_ci:
                    edge_push[eidx] = push
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
                divisor = no if isinstance(bld, BuildingSplitter) and no > 0 else 1
                ti_push = ti_in / divisor
                ax_push = ax_in / divisor
                rax_push = rax_in / divisor
                total_push = ti_push + ax_push + rax_push
                total_out = 0.0
                for oi, eidx in edges_ci:
                    edge_push[eidx] = total_push
                    f_ti[oi] += ti_push
                    f_ax[oi] += ax_push
                    f_rax[oi] += rax_push
                    f_total[oi] += total_push
                    total_out += total_push
                    in_degree[oi] -= 1
                    if in_degree[oi] <= 0:
                        queue.append(oi)
                incoming = ti_in + ax_in + rax_in
                f_ti_excess[ci] = ti_in - ti_push * no
                f_ax_excess[ci] = ax_in - ax_push * no
                f_rax_excess[ci] = rax_in - rax_push * no
                f_excess[ci] = incoming - total_out

            case BuildingCore():
                pass  # Core absorbs all flow (Ti delivered = victory points)

            case BuildingGunner() | BuildingSentinel() | BuildingBreach() | BuildingLauncher():
                # Turrets consume Ti for ammo: 0.2 Ti/round (2 Ti per shot, stack of 10)
                # Mark surplus flow as excess on this tile
                ti_in = f_ti[ci]
                consumption = 0.2
                f_ti_excess[ci] = max(0.0, ti_in - consumption)
                f_excess[ci] = f_ti_excess[ci]

    _t3 = _t()
    # Backward pass: attribute flow to friendly/enemy sinks
    sink_set = set(turret_idx) | set(core_idx)
    for i in sink_set:
        bld = building[i]
        if bld is not None and bld.team == my_team:
            f_my_frac[i] = 1.0
        elif bld is not None:
            f_en_frac[i] = 1.0

    for ci in reversed(topo_order):
        edges_ci = out_edges[ci]
        no = len(edges_ci)
        if ci in sink_set or no == 0:
            continue
        my_w = 0.0
        en_w = 0.0
        total_w = 0.0
        for oi, eidx in edges_ci:
            ep = edge_push[eidx]
            my_w += ep * f_my_frac[oi]
            en_w += ep * f_en_frac[oi]
            total_w += ep
        if total_w > 0:
            f_my_frac[ci] = my_w / total_w
            f_en_frac[ci] = en_w / total_w

    for i in chain(*_all):
        f_my_total[i] = f_total[i] * f_my_frac[i]
        f_en_total[i] = f_total[i] * f_en_frac[i]

    # Blocked propagation
    for i in chain(*_recv):
        f_blocked[i] = False
    seeds: deque[int] = deque()
    for i in chain(*_recv):
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
    _t4 = _t()
