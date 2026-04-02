__all__ = ["update"]

from attack_patterns import (
    BREACH_OFFSETS,
    GUNNER_OFFSETS,
    LAUNCHER_OFFSETS,
    SENTINEL_OFFSETS,
)
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
from marker import MarkerEureka, MarkerTaskClaim, is_stale
from marker import decode as decode_marker
from util import COST_IMPASSABLE, Symmetry

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
    """
    This is the main update function
    The state should only be updated by calling this function once per turn
    Don't do any other updates to state outside of this function!
    """
    state.age += 1
    state.pos = ct.get_position()

    t0 = ct.get_cpu_time_elapsed()
    _update_core_hp(state, ct)
    _update_ephemeral(state, ct)
    t1 = ct.get_cpu_time_elapsed()
    changed = _scan_vision(state, ct)
    _stamp_unit_tiles(state)
    t2 = ct.get_cpu_time_elapsed()
    _update_flow(state, ct, changed)
    t3 = ct.get_cpu_time_elapsed()
    _update_infra_staleness(state)
    t4 = ct.get_cpu_time_elapsed()
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
    w = state.w

    for p in state.unit_tiles:
        state.update_cost(p.y * w + p.x)
    state.unit_tiles.clear()

    my_id = ct.get_id()
    for uid in ct.get_nearby_units():
        if uid == my_id:
            continue
        state.unit_tiles.add(ct.get_position(uid))

    state.claims = {c for c in state.claims if not is_stale(c, rnd)}


def _stamp_unit_tiles(state: State) -> None:
    w = state.w
    cost = state.cost
    for p in state.unit_tiles:
        cost[p.y * w + p.x] = COST_IMPASSABLE


def _scan_vision(state: State, ct: Controller) -> list[int]:
    w = state.w
    changed: list[int] = []
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
                state.ore_ti.add(i)
            case Environment.ORE_AXIONITE:
                state.ore_ax.add(i)

        bid = ct.get_tile_building_id(t)
        if bid is not None:
            etype = ct.get_entity_type(bid)
            bld = _make_building(ct, bid, etype)
            state.building[i] = bld
            _update_sets(state, i, old_bld, bld)
            if bld != old_bld or env != old_env:
                changed.append(i)

            match bld:
                case BuildingMarker(team) if team == state.my_team:
                    msg = decode_marker(bld.value)
                    match msg:
                        case MarkerTaskClaim() if not is_stale(msg, rnd):
                            state.claims.add(msg)
                        case MarkerEureka() if state.symmetry is None:
                            state.symmetry = Symmetry(msg.symmetry)
                case BuildingCore(team) if team != state.my_team:
                    state.en_core_tiles.add(i)
        else:
            state.building[i] = None
            _update_sets(state, i, old_bld, None)
            if old_bld is not None or env != old_env:
                changed.append(i)

        state.update_cost(i)
        new_tiles.append((t, env))

    _apply_symmetry(state, new_tiles)
    _drain_reflect_queue(state)
    return changed


def _classify(bld: Building | None) -> str | None:
    """
    See method below
    """
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


def _turret_offsets(bld: Building) -> tuple[tuple[int, int], ...] | None:
    match bld:
        case BuildingGunner(direction=d):
            return GUNNER_OFFSETS[d]
        case BuildingSentinel(direction=d):
            return SENTINEL_OFFSETS[d]
        case BuildingBreach(direction=d):
            return BREACH_OFFSETS[d]
        case BuildingLauncher():
            return LAUNCHER_OFFSETS
    return None


def _apply_threat(state: State, idx: int, bld: Building, sign: int) -> None:
    offsets = _turret_offsets(bld)
    if offsets is None:
        return
    w, h = state.w, state.h
    px, py = idx % w, idx // w
    if bld.team == state.my_team:
        arr = state.my_threat
    else:
        match bld:
            case BuildingGunner():
                arr = state.en_gunner
            case BuildingSentinel():
                arr = state.en_sentinel
            case BuildingBreach():
                arr = state.en_breach
            case BuildingLauncher():
                arr = state.en_launcher
            case _:
                return
    for dx, dy in offsets:
        x, y = px + dx, py + dy
        if 0 <= x < w and 0 <= y < h:
            arr[y * w + x] += sign


def _update_sets(
    state: State,
    idx: int,
    old_bld: Building | None,
    new_bld: Building | None,
) -> None:
    """
    We store a lot of sets of important tiles all the time, like where the ores are, where our turrets are etc.
    We want to update them incrementally
    Here we do that

    This looks really fucking stupid, constructing the attribute names dynamically, but it turns out that
    python stores everything in dicts anyway, so writing it fully like a normal person doesn't fucking help,
    and this doesn't hurt performance
    """
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
        if old_cat == "turrets":
            _apply_threat(state, p, old_bld, -1)

    if new_cat is not None and new_bld is not None:
        getattr(state, new_cat).add(p)
        prefix = "my_" if new_bld.team == my_team else "en_"
        getattr(state, prefix + new_cat).add(p)
        if new_cat == "turrets":
            _apply_threat(state, p, new_bld, +1)


_REFLECT_BUDGET = 25


def _apply_symmetry(
    state: State,
    new_tiles: list[tuple[Position, Environment]],
) -> None:
    had_symmetry = state.symmetry is not None
    if not had_symmetry:
        _eliminate_symmetries(state, new_tiles)
    if state.symmetry is None:
        return
    w = state.w
    if had_symmetry:
        source = new_tiles
    else:
        source = [
            (Position(i % w, i // w), e)
            for i, e in enumerate(state.env)
            if e is not None
        ]
    pending = state.reflect_queue
    for t, env in source:
        m = mirror(state, t)
        mi = m.y * w + m.x
        if state.env[mi] is not None:
            continue
        state.env[mi] = env
        match env:
            case Environment.ORE_TITANIUM:
                state.ore_ti.add(mi)
            case Environment.ORE_AXIONITE:
                state.ore_ax.add(mi)
        pending.append(mi)


def _drain_reflect_queue(state: State) -> None:
    pending = state.reflect_queue
    if not pending:
        return
    n = min(len(pending), _REFLECT_BUDGET)
    for _ in range(n):
        state.update_cost(pending.popleft())


def _eliminate_symmetries(
    state: State,
    new_tiles: list[tuple[Position, Environment]],
) -> None:
    """
    See those new tile? Do they contradict any hypotheses about the symmetry of the map?
    """
    w, h = state.w, state.h
    to_remove: set[Symmetry] = set()
    cx, cy = state.my_core.x, state.my_core.y

    if state.en_core_tiles:
        for sym in state.symmetry_candidates:
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
        for sym in state.symmetry_candidates:
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
        for sym in state.symmetry_candidates - to_remove:
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

    state.symmetry_candidates -= to_remove

    if len(state.symmetry_candidates) == 1:
        state.symmetry = next(iter(state.symmetry_candidates))
    elif len(state.symmetry_candidates) > 1:
        seen = sum(1 for e in state.env if e is not None)
        if seen > state.w * state.h // 2:
            state.symmetry = next(iter(state.symmetry_candidates))


def _update_flow(state: State, ct: Controller, changed: list[int]) -> None:
    """
    Use the flow update algorithm defined in another file, but only if we actually need to
    We don't need to recalculate if nothing related to transport changed in our vision
    """
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
        # state.leakage_mask = build_leakage_mask(state)
    elif state.leakage_mask is None:
        # state.leakage_mask = build_leakage_mask(state)
        pass


def _update_infra_staleness(state: State) -> None:
    """
    We track the last time we saw each tile.
    Empirically our buildings are (hopefully) more important to check than tiles without our buildings.
    Define staleness of a tile sa as current round - last time you saw that tile.
    Max staleness for all of our buildings is a good heuristic to prioritise patrolling.
    "Hey, I haven't looked at this area in a while"
    """
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
