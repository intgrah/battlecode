__all__ = ["update"]

from building import (
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
    BuildingRoad,
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
from .state_update_econ import update_en_econ, update_my_econ

_ETYPE_TO_BUILDING: dict[EntityType, type] = {
    EntityType.CORE: BuildingCore,
    EntityType.HARVESTER: BuildingHarvester,
    EntityType.CONVEYOR: BuildingConveyor,
    EntityType.ARMOURED_CONVEYOR: BuildingArmouredConveyor,
    EntityType.SPLITTER: BuildingSplitter,
    EntityType.BRIDGE: BuildingBridge,
    EntityType.FOUNDRY: BuildingFoundry,
    EntityType.BARRIER: BuildingBarrier,
    EntityType.ROAD: BuildingRoad,
    EntityType.MARKER: BuildingMarker,
    EntityType.GUNNER: BuildingGunner,
    EntityType.SENTINEL: BuildingSentinel,
    EntityType.BREACH: BuildingBreach,
    EntityType.LAUNCHER: BuildingLauncher,
}


def _make_building(ct: Controller, bid: int, etype: EntityType) -> Building | None:
    team = ct.get_team(bid)
    match etype:
        case EntityType.CONVEYOR | EntityType.ARMOURED_CONVEYOR | EntityType.SPLITTER:
            cls = _ETYPE_TO_BUILDING[etype]
            return cls(team, ct.get_direction(bid))
        case EntityType.GUNNER | EntityType.SENTINEL | EntityType.BREACH:
            cls = _ETYPE_TO_BUILDING[etype]
            return cls(team, ct.get_direction(bid))
        case EntityType.BRIDGE:
            return BuildingBridge(team, ct.get_bridge_target(bid))
        case EntityType.MARKER:
            return BuildingMarker(team, ct.get_marker_value(bid))
        case _:
            cls = _ETYPE_TO_BUILDING.get(etype)
            if cls is None:
                return None
            return cls(team)


def update(state: State, ct: Controller) -> None:
    state.age += 1
    state.pos = ct.get_position()

    _update_core_hp(state, ct)
    _update_ephemeral(state, ct)
    changed = _scan_vision(state, ct)
    _rebuild_sets(state)
    _update_flow(state, changed)


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
            if old_bld is not None or env != old_env:
                changed.append(t)

        new_tiles.append((t, env))

    _update_symmetry(state, new_tiles)
    return changed


def _rebuild_sets(state: State) -> None:
    w = state.w
    n = w * state.h
    my_team = state.my_team

    state.my_harvesters.clear()
    state.my_transport.clear()
    state.my_foundries.clear()
    state.my_turrets.clear()
    state.my_barriers.clear()
    state.en_harvesters.clear()
    state.en_transport.clear()
    state.en_foundries.clear()
    state.en_turrets.clear()
    state.en_barriers.clear()

    for i in range(n):
        bld = state.building[i]
        if bld is None:
            continue
        p = Position(i % w, i // w)

        if bld.team == my_team:
            match bld:
                case BuildingHarvester():
                    state.my_harvesters.add(p)
                case (
                    BuildingConveyor()
                    | BuildingArmouredConveyor()
                    | BuildingSplitter()
                    | BuildingBridge()
                ):
                    state.my_transport.add(p)
                case BuildingFoundry():
                    state.my_foundries.add(p)
                case (
                    BuildingGunner()
                    | BuildingSentinel()
                    | BuildingBreach()
                    | BuildingLauncher()
                ):
                    state.my_turrets.add(p)
                case BuildingBarrier():
                    state.my_barriers.add(p)
        else:
            match bld:
                case BuildingHarvester():
                    state.en_harvesters.add(p)
                case (
                    BuildingConveyor()
                    | BuildingArmouredConveyor()
                    | BuildingSplitter()
                    | BuildingBridge()
                ):
                    state.en_transport.add(p)
                case BuildingFoundry():
                    state.en_foundries.add(p)
                case (
                    BuildingGunner()
                    | BuildingSentinel()
                    | BuildingBreach()
                    | BuildingLauncher()
                ):
                    state.en_turrets.add(p)
                case BuildingBarrier():
                    state.en_barriers.add(p)


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
        update_my_econ(state)
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
        update_en_econ(state)
