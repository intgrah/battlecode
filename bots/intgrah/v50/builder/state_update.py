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
    print(
        f"  ephemeral={t1 - t0}us scan={t2 - t1}us"
        f" flow={t3 - t2}us stale={t4 - t3}us"
    )


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


def _scan_vision(state: State, ct: Controller) -> list[Position]:
    w = state.w
    changed: list[Position] = []
    new_tiles: list[tuple[Position, Environment]] = []
    rnd = ct.get_current_round()

    for t in ct.get_nearby_tiles():
        i = t.y * w + t.x
        state.last_seen[i] = rnd

        old_env = state.env[i]
        old_bld = state.building[i]
        state.env[i] = env = ct.get_tile_env(t)

        match env:
            case Environment.ORE_TITANIUM:
                state.ore_ti.add(t)
            case Environment.ORE_AXIONITE:
                state.ore_ax.add(t)

        bid = ct.get_tile_building_id(t)
        if bid is not None:
            etype = ct.get_entity_type(bid)
            bld = _make_building(ct, bid, etype)
            state.building[i] = bld
            _update_sets(state, t, old_bld, bld)
            if bld != old_bld or env != old_env:
                changed.append(t)

            match bld:
                case BuildingMarker(team) if team == state.my_team:
                    msg = decode_marker(bld.value)
                    match msg:
                        case MarkerTaskClaim() if not is_stale(msg, rnd):
                            state.claims.add(msg)
                        case MarkerEureka() if state.symmetry is None:
                            state.symmetry = Symmetry(msg.symmetry)
                            _reflect_all(state)
                case BuildingCore(team) if team != state.my_team:
                    state.en_core_tiles.add(t)
        else:
            state.building[i] = None
            _update_sets(state, t, old_bld, None)
            if old_bld is not None or env != old_env:
                changed.append(t)

        new_tiles.append((t, env))

    _update_symmetry(state, new_tiles)
    return changed


def _classify(bld: Building | None, my_team: object) -> str | None:
    if bld is None:
        return None
    if bld.team == my_team:
        match bld:
            case BuildingHarvester():
                return "my_harvesters"
            case (
                BuildingConveyor()
                | BuildingArmouredConveyor()
                | BuildingSplitter()
                | BuildingBridge()
            ):
                return "my_transport"
            case BuildingFoundry():
                return "my_foundries"
            case (
                BuildingGunner()
                | BuildingSentinel()
                | BuildingBreach()
                | BuildingLauncher()
            ):
                return "my_turrets"
            case BuildingBarrier():
                return "my_barriers"
    else:
        match bld:
            case BuildingHarvester():
                return "en_harvesters"
            case (
                BuildingConveyor()
                | BuildingArmouredConveyor()
                | BuildingSplitter()
                | BuildingBridge()
            ):
                return "en_transport"
            case BuildingFoundry():
                return "en_foundries"
            case (
                BuildingGunner()
                | BuildingSentinel()
                | BuildingBreach()
                | BuildingLauncher()
            ):
                return "en_turrets"
            case BuildingBarrier():
                return "en_barriers"
    return None


def _update_sets(state: State, p: Position, old_bld: Building | None, new_bld: Building | None) -> None:
    my_team = state.my_team
    old_cat = _classify(old_bld, my_team)
    new_cat = _classify(new_bld, my_team)
    if old_cat == new_cat:
        return
    if old_cat is not None:
        getattr(state, old_cat).discard(p)
    if new_cat is not None:
        getattr(state, new_cat).add(p)


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
                        state.ore_ti.add(m)
                    case Environment.ORE_AXIONITE:
                        state.ore_ax.add(m)


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
                    state.ore_ti.add(m)
                case Environment.ORE_AXIONITE:
                    state.ore_ax.add(m)


def _update_flow(state: State, ct: Controller, changed: list[Position]) -> None:
    infra = (
        state.my_transport | state.my_harvesters | state.my_foundries
        | state.my_turrets | state.my_core_tiles
        | state.en_transport | state.en_harvesters | state.en_foundries
        | state.en_turrets | state.en_core_tiles
    )
    needs_reflow = any(p in infra for p in changed)
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
    for p in state.my_transport:
        s = age - state.last_seen[state.idx(p.x, p.y)]
        if s > worst:
            worst = s
    for p in state.my_turrets:
        s = age - state.last_seen[state.idx(p.x, p.y)]
        if s > worst:
            worst = s
    for p in state.my_core_tiles:
        s = age - state.last_seen[state.idx(p.x, p.y)]
        if s > worst:
            worst = s
    state.infra_max_staleness = worst
