"""Per-turn belief update. Mutates state from controller vision."""

from cambc import Controller, EntityType, Environment
from flow_astar import build_leakage_mask
from marker import Eureka, TaskClaim, is_stale
from marker import decode as decode_marker
from util import DIRECTED_BUILDINGS, TRANSPORT, TURRETS, tiles_3x3

from .state import Symmetry, State
from .state_helpers import mirror
from .state_update_flow import recompute_enemy_flow, recompute_flow


def update(state: State, ct: Controller) -> None:
    """Incorporate all visible tiles into the state. Call once per turn.

    Handles vision scan, symmetry detection, flow recomputation,
    cache invalidation, and leakage mask rebuild internally.
    """
    state.age += 1
    state.pos = ct.get_position()
    rnd = ct.get_current_round()
    w, h = state.w, state.h
    new_tiles: list[tuple[int, int, Environment]] = []
    changed: list[tuple[int, int]] = []

    state.unit_tiles.clear()
    my_id = ct.get_id()
    for uid in ct.get_nearby_units():
        if uid == my_id:
            continue
        upos = ct.get_position(uid)
        state.unit_tiles.add(upos.y * w + upos.x)

    state.claims = {c for c in state.claims if not is_stale(c, rnd)}

    for t in ct.get_nearby_tiles():
        x, y = t.x, t.y
        i = y * w + x
        state.last_seen[i] = rnd

        old_env = state.env[i]
        old_ent = state.entity[i]
        env = ct.get_tile_env(t)
        state.env[i] = env

        if env == Environment.ORE_TITANIUM:
            state.ore_ti.add((x, y))
        elif env == Environment.ORE_AXIONITE:
            state.ore_ax.add((x, y))

        bid = ct.get_tile_building_id(t)
        if bid is not None:
            etype = ct.get_entity_type(bid)
            team = ct.get_team(bid)
            new_ent = (etype, team)
            state.entity[i] = new_ent
            if new_ent != old_ent or env != old_env:
                changed.append((x, y))

            if etype in DIRECTED_BUILDINGS:
                state.direction[i] = ct.get_direction(bid)
                state.bridge_target[i] = None
            elif etype == EntityType.BRIDGE:
                state.direction[i] = None
                bt = ct.get_bridge_target(bid)
                state.bridge_target[i] = (bt.x, bt.y)
            else:
                state.direction[i] = None
                state.bridge_target[i] = None

            if team == state.my_team:
                if etype == EntityType.HARVESTER:
                    state.my_harvested.add((x, y))
                    state.my_harvesters.add(i)
                    state.my_transport.discard(i)
                    state.my_foundries.discard(i)
                elif etype in TRANSPORT:
                    state.my_transport.add(i)
                    state.my_harvesters.discard(i)
                    state.my_foundries.discard(i)
                elif etype == EntityType.FOUNDRY:
                    state.my_foundries.add(i)
                    state.my_transport.discard(i)
                    state.my_harvesters.discard(i)
                elif etype in TURRETS:
                    state.my_turrets.add(i)
                elif etype == EntityType.MARKER:
                    msg = decode_marker(ct.get_marker_value(bid))
                    if isinstance(msg, TaskClaim) and not is_stale(msg, rnd):
                        state.claims.add(msg)
                    elif isinstance(msg, Eureka) and state.symmetry is None:
                        state.symmetry = Symmetry(msg.symmetry)
                        _reflect_all(state)
                else:
                    state.my_transport.discard(i)
                    state.my_harvesters.discard(i)
                    state.my_foundries.discard(i)
                state.en_transport.discard(i)
                state.en_harvesters.discard(i)
                state.en_turrets.discard(i)
            else:
                if etype == EntityType.HARVESTER:
                    state.en_harvested.add((x, y))
                    state.en_harvesters.add(i)
                    state.en_transport.discard(i)
                    state.en_foundries.discard(i)
                elif etype in TRANSPORT:
                    state.en_transport.add(i)
                    state.en_harvesters.discard(i)
                    state.en_foundries.discard(i)
                elif etype == EntityType.FOUNDRY:
                    state.en_foundries.add(i)
                    state.en_transport.discard(i)
                    state.en_harvesters.discard(i)
                elif etype in TURRETS:
                    state.en_turrets.add(i)
                else:
                    state.en_transport.discard(i)
                    state.en_harvesters.discard(i)
                    state.en_foundries.discard(i)
                state.my_transport.discard(i)
                state.my_harvesters.discard(i)
                state.my_turrets.discard(i)

            if (
                state.en_core is None
                and etype == EntityType.CORE
                and team != state.my_team
            ):
                center = ct.get_position(bid)
                state.en_core = (center.x, center.y)
                state.en_core_tiles = tiles_3x3(center.x, center.y, w, h)
        else:
            state.entity[i] = None
            state.direction[i] = None
            state.bridge_target[i] = None
            state.my_harvested.discard((x, y))
            state.en_harvested.discard((x, y))
            state.my_transport.discard(i)
            state.my_harvesters.discard(i)
            state.my_turrets.discard(i)
            state.en_transport.discard(i)
            state.en_harvesters.discard(i)
            state.en_turrets.discard(i)
            if old_ent is not None or env != old_env:
                changed.append((x, y))

        new_tiles.append((x, y, env))

    if state.symmetry is None:
        _eliminate_symmetries(state, new_tiles)

    if state.symmetry is not None:
        for x, y, env in new_tiles:
            mx, my = mirror(state, x, y)
            mi = my * w + mx
            if state.env[mi] is None:
                state.env[mi] = env
                if env == Environment.ORE_TITANIUM:
                    state.ore_ti.add((mx, my))
                elif env == Environment.ORE_AXIONITE:
                    state.ore_ax.add((mx, my))

    needs_reflow = any(
        (ci := cy * w + cx) in state.my_transport
        or ci in state.my_harvesters
        or ci in state.my_foundries
        for cx, cy in changed
    )
    needs_enemy_reflow = any(
        (ci := cy * w + cx) in state.en_transport or ci in state.en_harvesters
        for cx, cy in changed
    )
    if needs_reflow:
        recompute_flow(state)
        state.ti_flow_search = None
        state.ti_cached_path = None
        state.ax_flow_search = None
        state.ax_cached_path = None
        state.leakage_mask = build_leakage_mask(state)
    elif state.leakage_mask is None:
        state.leakage_mask = build_leakage_mask(state)
    if needs_enemy_reflow:
        recompute_enemy_flow(state)


def _eliminate_symmetries(
    state: State,
    new_tiles: list[tuple[int, int, Environment]],
) -> None:
    w, h = state.w, state.h
    to_remove: set[Symmetry] = set()

    if state.en_core is not None:
        cx, cy = state.my_core
        ex, ey = state.en_core
        for sym in state.sym_candidates:
            match sym:
                case Symmetry.ROT:
                    px, py = w - 1 - cx, h - 1 - cy
                case Symmetry.HOR:
                    px, py = cx, h - 1 - cy
                case Symmetry.VER:
                    px, py = w - 1 - cx, cy
            if (px, py) != (ex, ey):
                to_remove.add(sym)
    else:
        cx, cy = state.my_core
        for sym in state.sym_candidates:
            match sym:
                case Symmetry.HOR:
                    if cy == h - 1 - cy:
                        to_remove.add(sym)
                case Symmetry.VER:
                    if cx == w - 1 - cx:
                        to_remove.add(sym)
                case Symmetry.ROT:
                    pass

    for x, y, env in new_tiles:
        for sym in state.sym_candidates - to_remove:
            match sym:
                case Symmetry.ROT:
                    mx, my = w - 1 - x, h - 1 - y
                case Symmetry.HOR:
                    mx, my = x, h - 1 - y
                case Symmetry.VER:
                    mx, my = w - 1 - x, y
            mi = my * w + mx
            mirror_env = state.env[mi]
            if mirror_env is not None and mirror_env != env:
                to_remove.add(sym)

    state.sym_candidates -= to_remove

    if len(state.sym_candidates) == 1:
        state.symmetry = next(iter(state.sym_candidates))
        _reflect_all(state)
    elif len(state.sym_candidates) > 1:
        seen = sum(1 for e in state.env if e is not None)
        if seen > state.w * state.h // 2:
            state.symmetry = next(iter(state.sym_candidates))
            _reflect_all(state)


def _reflect_all(state: State) -> None:
    w = state.w
    for i in range(state.w * state.h):
        env = state.env[i]
        if env is None:
            continue
        x, y = i % w, i // w
        mx, my = mirror(state, x, y)
        mi = my * w + mx
        if state.env[mi] is None:
            state.env[mi] = env
            if env == Environment.ORE_TITANIUM:
                state.ore_ti.add((mx, my))
            elif env == Environment.ORE_AXIONITE:
                state.ore_ax.add((mx, my))
