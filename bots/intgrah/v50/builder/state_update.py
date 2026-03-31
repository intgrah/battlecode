__all__ = ["update"]

from building import (
    ETYPE_BUILDING,
    Building,
    BuildingArmouredConveyor,
    BuildingBarrier,
    BuildingBreach,
    BuildingBridge,
    BuildingConveyor,
    BuildingCore,
    BuildingFoundry,
    BuildingGunner,
    BuildingHarvester,
    BuildingLauncher,
    BuildingMarker,
    BuildingSentinel,
    BuildingSplitter,
)
from cambc import Controller, EntityType, Environment, Position
from flow_astar import build_leakage_mask
from marker import MarkerEureka, MarkerTaskClaim, is_stale
from marker import decode as decode_marker
from util import Symmetry

from .state import State
from .state_helpers import mirror
from .state_update_econ import update_flow


def _make_building(ct: Controller, bid: int, etype: EntityType) -> Building | None:
    team = ct.get_team(bid)
    match etype:
        case EntityType.CONVEYOR | EntityType.ARMOURED_CONVEYOR | EntityType.SPLITTER:
            cls = ETYPE_BUILDING[etype]
            return cls(team, ct.get_direction(bid))
        case EntityType.GUNNER | EntityType.SENTINEL | EntityType.BREACH:
            cls = ETYPE_BUILDING[etype]
            return cls(team, ct.get_direction(bid))
        case EntityType.BRIDGE:
            return BuildingBridge(team, ct.get_bridge_target(bid))
        case EntityType.MARKER:
            if team == ct.get_team():
                return BuildingMarker(team, ct.get_marker_value(bid))
            return BuildingMarker(team, 0)
        case _:
            cls = ETYPE_BUILDING.get(etype)
            if cls is None:
                return None
            return cls(team)


def update(state: State, ct: Controller) -> None:
    state.age += 1
    state.pos = ct.get_position()

    t = ct.get_cpu_time_elapsed
    t0 = t()
    _update_core_hp(state, ct)
    _update_ephemeral(state, ct)
    t1 = t()
    changed = _scan_vision(state, ct)
    t2 = t()
    _update_flow(state, ct, changed)
    t3 = t()
    _update_infra_staleness(state)
    t4 = t()
    print(f"  ephemeral={t1 - t0}us")
    print(f"  scan={t2 - t1}us")
    print(f"  flow={t3 - t2}us")
    print(f"  stale={t4 - t3}us")


def _update_core_hp(state: State, ct: Controller) -> None:
    core = state.my_core
    if not ct.is_in_vision(core):
        return
    bid = ct.get_tile_building_id(core)
    if bid is None:
        return
    state.my_core_hp = ct.get_hp(bid)


def _update_ephemeral(state: State, ct: Controller) -> None:
    rnd = ct.get_current_round()
    state.unit_tiles.clear()
    my_id = ct.get_id()
    for uid in ct.get_nearby_units():
        if uid == my_id:
            continue
        state.unit_tiles.add(ct.get_position(uid))
    state.claims = {c for c in state.claims if not is_stale(c, rnd)}


def _scan_vision(state: State, ct: Controller) -> list[int]:
    w = state.w
    changed: list[int] = []
    new_tiles: list[tuple[Position, Environment]] = []
    rnd = ct.get_current_round()

    _g = ct.get_cpu_time_elapsed
    t_api = 0
    t_make = 0
    t_sets = 0
    t_eq = 0
    t_marker = 0
    t_sym = 0
    t_rest = 0
    n_tiles = 0
    n_bld = 0
    n_markers = 0

    for t in ct.get_nearby_tiles():
        n_tiles += 1
        _s0 = _g()
        i = t.y * w + t.x
        state.last_seen[i] = rnd

        old_env = state.env[i]
        old_bld = state.building[i]
        state.env[i] = env = ct.get_tile_env(t)

        match env:
            case Environment.ORE_TITANIUM:
                state.ore_ti.add(i)
            case Environment.ORE_AXIONITE:
                state.ore_ax.add(i)

        bid = ct.get_tile_building_id(t)
        _s1 = _g()
        t_api += _s1 - _s0
        if bid is not None:
            n_bld += 1
            etype = ct.get_entity_type(bid)
            bld = _make_building(ct, bid, etype)
            _s2 = _g()
            t_make += _s2 - _s1
            state.building[i] = bld
            _update_sets(state, i, old_bld, bld)
            _s3 = _g()
            t_sets += _s3 - _s2
            _eq = bld != old_bld or env != old_env
            _s4 = _g()
            t_eq += _s4 - _s3
            if _eq:
                changed.append(i)

            match bld:
                case BuildingMarker(team) if team == state.my_team:
                    n_markers += 1
                    msg = decode_marker(bld.value)
                    match msg:
                        case MarkerTaskClaim() if not is_stale(msg, rnd):
                            state.claims.add(msg)
                        case MarkerEureka() if state.symmetry is None:
                            state.symmetry = Symmetry(msg.symmetry)
                            _reflect_all(state)
                case BuildingCore(team) if team != state.my_team:
                    state.en_core_tiles.add(i)
            t_marker += _g() - _s4
        else:
            state.building[i] = None
            _update_sets(state, i, old_bld, None)
            if old_bld is not None or env != old_env:
                changed.append(i)
            t_rest += _g() - _s1

        new_tiles.append((t, env))

    _ss = _g()
    _update_symmetry(state, new_tiles)
    t_sym = _g() - _ss
    print(
        f"    scan: tiles={n_tiles} bld={n_bld} markers={n_markers}"
        f" api={t_api}us make={t_make}us sets={t_sets}us"
        f" eq={t_eq}us marker={t_marker}us sym={t_sym}us rest={t_rest}us"
    )
    return changed


def _classify(bld: Building | None) -> str | None:
    if bld is None:
        return None
    match bld:
        case BuildingHarvester():
            return "harvesters"
        case (
            BuildingConveyor()
            | BuildingArmouredConveyor()
            | BuildingSplitter()
            | BuildingBridge()
        ):
            return "transport"
        case BuildingFoundry():
            return "foundries"
        case (
            BuildingGunner()
            | BuildingSentinel()
            | BuildingBreach()
            | BuildingLauncher()
        ):
            return "turrets"
        case BuildingBarrier():
            return "barriers"
    return None


def _update_sets(
    state: State,
    idx: int,
    old_bld: Building | None,
    new_bld: Building | None,
) -> None:
    p = idx
    my_team = state.my_team
    old_cat = _classify(old_bld)
    new_cat = _classify(new_bld)
    if old_cat == new_cat and (
        old_bld is None or new_bld is None or old_bld.team == new_bld.team
    ):
        return

    if old_cat is not None and old_bld is not None:
        getattr(state, old_cat).discard(p)
        prefix = "my_" if old_bld.team == my_team else "en_"
        getattr(state, prefix + old_cat).discard(p)

    if new_cat is not None and new_bld is not None:
        getattr(state, new_cat).add(p)
        prefix = "my_" if new_bld.team == my_team else "en_"
        getattr(state, prefix + new_cat).add(p)


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
                match env:
                    case Environment.ORE_TITANIUM:
                        state.ore_ti.add(mi)
                    case Environment.ORE_AXIONITE:
                        state.ore_ax.add(mi)


def _eliminate_symmetries(
    state: State,
    new_tiles: list[tuple[Position, Environment]],
) -> None:
    w, h = state.w, state.h
    to_remove: set[Symmetry] = set()
    cx, cy = state.my_core.x, state.my_core.y

    if state.en_core_tiles:
        for sym in state.sym_candidates:
            match sym:
                case Symmetry.ROT:
                    px, py = w - 1 - cx, h - 1 - cy
                case Symmetry.HOR:
                    px, py = cx, h - 1 - cy
                case Symmetry.VER:
                    px, py = w - 1 - cx, cy
            if Position(px, py) not in state.en_core_tiles:
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
            match env:
                case Environment.ORE_TITANIUM:
                    state.ore_ti.add(mi)
                case Environment.ORE_AXIONITE:
                    state.ore_ax.add(mi)


def _update_flow(state: State, ct: Controller, changed: list[int]) -> None:
    infra = state.transport | state.harvesters | state.foundries | state.turrets
    needs_reflow = any(i in infra for i in changed)
    if not needs_reflow and changed:
        print(f"  no_reflow: changed={len(changed)} infra={len(infra)}")
    if needs_reflow:
        t0 = ct.get_cpu_time_elapsed()
        update_flow(state)
        print(f"  econ={ct.get_cpu_time_elapsed() - t0}us")
        state.ti_flow_search = None
        state.ti_cached_path = None
        state.ax_flow_search = None
        state.ax_cached_path = None
        state.bridge_flow_search = None
        state.bridge_cached_path = None
        state.leakage_mask = build_leakage_mask(state)
    elif state.leakage_mask is None:
        state.leakage_mask = build_leakage_mask(state)


def _update_infra_staleness(state: State) -> None:
    age = state.age
    worst = 0
    for i in state.my_transport:
        s = age - state.last_seen[i]
        worst = max(worst, s)
    for i in state.my_turrets:
        s = age - state.last_seen[i]
        worst = max(worst, s)
    for i in state.my_core_tiles:
        s = age - state.last_seen[i]
        worst = max(worst, s)
    state.infra_max_staleness = worst
