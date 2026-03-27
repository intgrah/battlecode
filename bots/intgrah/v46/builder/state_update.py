__all__ = ["update"]

from cambc import Controller, EntityType, Environment, Position
from flow_astar import build_leakage_mask
from marker import Eureka, TaskClaim, is_stale
from marker import decode as decode_marker
from util import DIRECTED_BUILDINGS, TRANSPORT, TURRETS, tiles_3x3

from .state import State, Symmetry
from .state_helpers import mirror
from .state_update_flow import recompute_enemy_flow, recompute_flow


def update(state: State, ct: Controller) -> None:
    state.age += 1
    state.pos = ct.get_position()
    rnd = ct.get_current_round()

    _update_ephemeral(state, ct, rnd)
    _update_core_hp(state, ct)
    changed, new_tiles = _scan_vision(state, ct, rnd)
    _update_symmetry(state, new_tiles)
    _update_flow(state, changed)


def _update_core_hp(state: State, ct: Controller) -> None:
    core = state.my_core
    if not ct.is_in_vision(core):
        return
    bid = ct.get_tile_building_id(core)
    if bid is None:
        return
    state.my_core_hp = ct.get_hp(bid)


def _update_ephemeral(state: State, ct: Controller, rnd: int) -> None:
    state.unit_tiles.clear()
    my_id = ct.get_id()
    for uid in ct.get_nearby_units():
        if uid == my_id:
            continue
        state.unit_tiles.add(ct.get_position(uid))
    state.claims = {c for c in state.claims if not is_stale(c, rnd)}


def _scan_vision(
    state: State,
    ct: Controller,
    rnd: int,
) -> tuple[list[Position], list[tuple[Position, Environment]]]:
    w = state.w
    changed: list[Position] = []
    new_tiles: list[tuple[Position, Environment]] = []

    for t in ct.get_nearby_tiles():
        i = t.y * w + t.x
        state.last_seen[i] = rnd

        old_env = state.env[i]
        old_ent = state.entity[i]
        env = ct.get_tile_env(t)
        state.env[i] = env

        if env == Environment.ORE_TITANIUM:
            state.ore_ti.add(t)
        elif env == Environment.ORE_AXIONITE:
            state.ore_ax.add(t)

        bid = ct.get_tile_building_id(t)
        if bid is not None:
            _process_building(state, ct, i, t, bid, old_ent, old_env, env, rnd, changed)
        else:
            _process_empty(state, i, t, old_ent, old_env, env, changed)

        new_tiles.append((t, env))

    return changed, new_tiles


def _process_building(
    state: State,
    ct: Controller,
    i: int,
    pos: Position,
    bid: int,
    old_ent: tuple[EntityType, ...] | None,
    old_env: Environment | None,
    env: Environment,
    rnd: int,
    changed: list[Position],
) -> None:
    etype = ct.get_entity_type(bid)
    team = ct.get_team(bid)
    new_ent = (etype, team)
    state.entity[i] = new_ent
    if new_ent != old_ent or env != old_env:
        changed.append(pos)

    if etype in DIRECTED_BUILDINGS:
        state.direction[i] = ct.get_direction(bid)
        state.bridge_target[i] = None
    elif etype == EntityType.BRIDGE:
        state.direction[i] = None
        state.bridge_target[i] = ct.get_bridge_target(bid)
    else:
        state.direction[i] = None
        state.bridge_target[i] = None

    if team == state.my_team:
        _classify_friendly(state, ct, pos, bid, etype, rnd)
        state.en_transport.discard(pos)
        state.en_harvesters.discard(pos)
        state.en_turrets.discard(pos)
        state.en_barriers.discard(pos)
    else:
        _classify_enemy(state, pos, etype)
        state.my_transport.discard(pos)
        state.my_harvesters.discard(pos)
        state.my_turrets.discard(pos)
        state.my_barriers.discard(pos)

    if state.en_core is None and etype == EntityType.CORE and team != state.my_team:
        center = ct.get_position(bid)
        state.en_core = center
        state.en_core_tiles = tiles_3x3(center, state.w, state.h)


def _classify_friendly(
    state: State,
    ct: Controller,
    pos: Position,
    bid: int,
    etype: EntityType,
    rnd: int,
) -> None:
    match etype:
        case EntityType.HARVESTER:
            state.my_harvested.add(pos)
            state.my_harvesters.add(pos)
            state.my_transport.discard(pos)
            state.my_foundries.discard(pos)
        case _ if etype in TRANSPORT:
            state.my_transport.add(pos)
            state.my_harvesters.discard(pos)
            state.my_foundries.discard(pos)
        case EntityType.FOUNDRY:
            state.my_foundries.add(pos)
            state.my_transport.discard(pos)
            state.my_harvesters.discard(pos)
        case _ if etype in TURRETS:
            state.my_turrets.add(pos)
        case EntityType.BARRIER:
            state.my_barriers.add(pos)
        case EntityType.MARKER:
            msg = decode_marker(ct.get_marker_value(bid))
            if isinstance(msg, TaskClaim) and not is_stale(msg, rnd):
                state.claims.add(msg)
            elif isinstance(msg, Eureka) and state.symmetry is None:
                state.symmetry = Symmetry(msg.symmetry)
                _reflect_all(state)
        case _:
            state.my_transport.discard(pos)
            state.my_harvesters.discard(pos)
            state.my_foundries.discard(pos)


def _classify_enemy(
    state: State,
    pos: Position,
    etype: EntityType,
) -> None:
    match etype:
        case EntityType.HARVESTER:
            state.en_harvested.add(pos)
            state.en_harvesters.add(pos)
            state.en_transport.discard(pos)
            state.en_foundries.discard(pos)
        case _ if etype in TRANSPORT:
            state.en_transport.add(pos)
            state.en_harvesters.discard(pos)
            state.en_foundries.discard(pos)
        case EntityType.FOUNDRY:
            state.en_foundries.add(pos)
            state.en_transport.discard(pos)
            state.en_harvesters.discard(pos)
        case _ if etype in TURRETS:
            state.en_turrets.add(pos)
        case EntityType.BARRIER:
            state.en_barriers.add(pos)
        case _:
            state.en_transport.discard(pos)
            state.en_harvesters.discard(pos)
            state.en_foundries.discard(pos)


def _process_empty(
    state: State,
    i: int,
    pos: Position,
    old_ent: tuple[EntityType, ...] | None,
    old_env: Environment | None,
    env: Environment,
    changed: list[Position],
) -> None:
    state.entity[i] = None
    state.direction[i] = None
    state.bridge_target[i] = None
    state.my_harvested.discard(pos)
    state.en_harvested.discard(pos)
    state.my_transport.discard(pos)
    state.my_harvesters.discard(pos)
    state.my_turrets.discard(pos)
    state.my_barriers.discard(pos)
    state.en_transport.discard(pos)
    state.en_harvesters.discard(pos)
    state.en_turrets.discard(pos)
    state.en_barriers.discard(pos)
    if old_ent is not None or env != old_env:
        changed.append(pos)


def _update_symmetry(
    state: State,
    new_tiles: list[tuple[Position, Environment]],
) -> None:
    w = state.w
    if state.symmetry is None:
        _eliminate_symmetries(state, new_tiles)
    if state.symmetry is not None:
        for t, env in new_tiles:
            m = mirror(state, t)
            mi = m.y * w + m.x
            if state.env[mi] is None:
                state.env[mi] = env
                if env == Environment.ORE_TITANIUM:
                    state.ore_ti.add(m)
                elif env == Environment.ORE_AXIONITE:
                    state.ore_ax.add(m)


def _eliminate_symmetries(
    state: State,
    new_tiles: list[tuple[Position, Environment]],
) -> None:
    w, h = state.w, state.h
    to_remove: set[Symmetry] = set()
    cx, cy = state.my_core.x, state.my_core.y

    if state.en_core is not None:
        ex, ey = state.en_core.x, state.en_core.y
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

    for t, env in new_tiles:
        for sym in state.sym_candidates - to_remove:
            match sym:
                case Symmetry.ROT:
                    mx, my = w - 1 - t.x, h - 1 - t.y
                case Symmetry.HOR:
                    mx, my = t.x, h - 1 - t.y
                case Symmetry.VER:
                    mx, my = w - 1 - t.x, t.y
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
        m = mirror(state, Position(i % w, i // w))
        mi = m.y * w + m.x
        if state.env[mi] is None:
            state.env[mi] = env
            if env == Environment.ORE_TITANIUM:
                state.ore_ti.add(m)
            elif env == Environment.ORE_AXIONITE:
                state.ore_ax.add(m)


def _update_flow(state: State, changed: list[Position]) -> None:
    needs_reflow = any(
        p in state.my_transport or p in state.my_harvesters or p in state.my_foundries
        for p in changed
    )
    needs_enemy_reflow = any(
        p in state.en_transport or p in state.en_harvesters for p in changed
    )
    if needs_reflow:
        recompute_flow(state)
        state.ti_flow_search = None
        state.ti_cached_path = None
        state.ax_flow_search = None
        state.ax_cached_path = None
        state.bridge_flow_search = None
        state.bridge_cached_path = None
        state.leakage_mask = build_leakage_mask(state)
    elif state.leakage_mask is None:
        state.leakage_mask = build_leakage_mask(state)
    if needs_enemy_reflow:
        recompute_enemy_flow(state)
