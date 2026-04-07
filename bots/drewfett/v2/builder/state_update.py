"""Vision scan and incremental state updates.

Simplified from rush: NO flow simulation. We track sets of harvesters,
transport, turrets etc. but don't compute flow magnitudes.
"""

__all__ = ["update"]

from collections import deque

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
from util import COST_IMPASSABLE, DIR4_DELTA, Symmetry

from .state import State
from .state_helpers import mirror


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
    """Main per-turn update. Call exactly once per round."""
    state.age += 1
    state.pos = ct.get_position()

    _update_core_hp(state, ct)
    _update_ephemeral(state, ct)
    new_tiles = _scan_vision(state, ct)
    _apply_symmetry(state, new_tiles)
    _drain_reflect_queue(state)
    _rebuild_danger_zones(state)
    _stamp_unit_tiles(state)
    _update_connectivity(state)
    _update_infra_staleness(state)


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
    my_team = state.my_team
    state.enemy_bots_nearby = False
    for uid in ct.get_nearby_units():
        if uid == my_id:
            continue
        state.unit_tiles.add(ct.get_position(uid))
        if ct.get_team(uid) != my_team:
            state.enemy_bots_nearby = True

    state.claims = {c for c in state.claims if not is_stale(c, rnd)}


def _scan_vision(
    state: State,
    ct: Controller,
) -> list[tuple[Position, Environment]]:
    w = state.w
    changed: list[int] = []
    new_tiles: list[tuple[Position, Environment]] = []
    rnd = ct.get_current_round()
    my_team = state.my_team

    for t in ct.get_nearby_tiles():
        i = t.y * w + t.x
        state.last_seen[i] = rnd

        old_env = state.env[i]
        env = ct.get_tile_env(t)

        if env != old_env:
            state.env[i] = env
            match env:
                case Environment.ORE_TITANIUM:
                    state.ore_ti.add(i)
                case Environment.ORE_AXIONITE:
                    state.ore_ax.add(i)

        bid = ct.get_tile_building_id(t)
        old_bld = state.building[i]
        if bid is not None:
            etype = ct.get_entity_type(bid)
            bld = _make_building(ct, bid, etype)
            if bld != old_bld or env != old_env:
                state.building[i] = bld
                _update_sets(state, i, old_bld, bld)
                changed.append(i)
                state.update_cost(i)

            match bld:
                case BuildingMarker(team) if team == my_team:
                    msg = decode_marker(bld.value)
                    match msg:
                        case MarkerTaskClaim() if not is_stale(msg, rnd):
                            state.claims.add(msg)
                        case MarkerEureka() if state.symmetry is None:
                            state.symmetry = Symmetry(msg.symmetry)
                case BuildingCore(team) if team != my_team:
                    state.en_core_tiles.add(i)
                    if state.en_core_pos is None:
                        state.en_core_pos = ct.get_position(bid)
        elif old_bld is not None or env != old_env:
            state.building[i] = None
            _update_sets(state, i, old_bld, None)
            changed.append(i)
            state.update_cost(i)

        new_tiles.append((t, env))

    return new_tiles


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
    """Incrementally update the category sets (harvesters, transport, etc.)."""
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


_REFLECT_BUDGET = 25


def _apply_symmetry(
    state: State,
    new_tiles: list[tuple[Position, Environment]],
) -> None:
    had_symmetry = state.symmetry is not None
    old_en_core = state.en_core_pos
    if not had_symmetry:
        _eliminate_symmetries(state, new_tiles)
    if state.symmetry is not None:
        # Only infer core from symmetry if we haven't directly observed it
        if not state.en_core_tiles:
            correct_pos = mirror(state, state.my_core)
            if state.en_core_pos != correct_pos:
                state.en_core_pos = correct_pos
    elif state.sym_candidates:
        # Compute candidate core positions for each remaining symmetry
        w, h = state.w, state.h
        cx, cy = state.my_core.x, state.my_core.y
        positions: list[tuple[int, int]] = []
        for sym in state.sym_candidates:
            match sym:
                case Symmetry.ROT:
                    positions.append((w - 1 - cx, h - 1 - cy))
                case Symmetry.HOR:
                    positions.append((cx, h - 1 - cy))
                case Symmetry.VER:
                    positions.append((w - 1 - cx, cy))
        unique = set(positions)
        if len(unique) == 1:
            pos = next(iter(unique))
            state.en_core_pos = Position(pos[0], pos[1])
        else:
            # Provisional: average of candidate positions
            avg_x = sum(p[0] for p in positions) // len(positions)
            avg_y = sum(p[1] for p in positions) // len(positions)
            state.en_core_pos = Position(avg_x, avg_y)
    # Invalidate explore target if enemy core estimate moved
    if state.en_core_pos != old_en_core:
        state.explore_target = None

    if state.symmetry is None:
        return
    w = state.w
    # Mirror only new tiles (no bulk mirror on first detection)
    pending = state.reflect_queue
    for t, env in new_tiles:
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
    """Eliminate symmetry hypotheses contradicted by observed tiles."""
    w, h = state.w, state.h
    to_remove: set[Symmetry] = set()
    cx, cy = state.my_core.x, state.my_core.y

    # Eliminate symmetries that predict enemy core at our core position
    for sym in state.sym_candidates:
        match sym:
            case Symmetry.ROT:
                px, py = w - 1 - cx, h - 1 - cy
            case Symmetry.HOR:
                px, py = cx, h - 1 - cy
            case Symmetry.VER:
                px, py = w - 1 - cx, cy
        if (px, py) == (cx, cy):
            to_remove.add(sym)

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
    elif len(state.sym_candidates) > 1:
        # Only lock if all remaining candidates agree on core position
        core_positions: set[tuple[int, int]] = set()
        for sym in state.sym_candidates:
            match sym:
                case Symmetry.ROT:
                    core_positions.add((w - 1 - cx, h - 1 - cy))
                case Symmetry.HOR:
                    core_positions.add((cx, h - 1 - cy))
                case Symmetry.VER:
                    core_positions.add((w - 1 - cx, cy))
        if len(core_positions) == 1:
            # All agree -- safe to lock any
            state.symmetry = next(iter(state.sym_candidates))


def _rebuild_danger_zones(state: State) -> None:
    """Mark tiles near enemy turrets as dangerous.

    Launchers: adjacent tiles stamped as COST_IMPASSABLE in cost array
    and grid (hard avoid).
    Gunners/sentinels/breach: tiles in their attack arc added to
    danger_zones (soft penalty via pathfinding).
    """
    w, h = state.w, state.h
    state.danger_zones = set()

    for ti in state.en_turrets:
        bld = state.building[ti]
        tx, ty = ti % w, ti // w

        match bld:
            case BuildingLauncher():
                # Hard block -- launcher throws adjacent builders
                grid = state.grid
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        nx, ny = tx + dx, ty + dy
                        if 0 <= nx < w and 0 <= ny < h:
                            ni = ny * w + nx
                            state.cost[ni] = COST_IMPASSABLE
                            if grid is not None:
                                grid.set_passable(ni, passable=False)

            case (
                BuildingGunner(direction=d)
                | BuildingSentinel(direction=d)
                | BuildingBreach(direction=d)
            ):
                ddx, ddy = d.delta()
                r_sq = 13 if isinstance(bld, (BuildingGunner, BuildingBreach)) else 32
                is_sentinel = isinstance(bld, BuildingSentinel)
                x, y = tx + ddx, ty + ddy
                while 0 <= x < w and 0 <= y < h:
                    if (x - tx) ** 2 + (y - ty) ** 2 > r_sq:
                        break
                    state.danger_zones.add(y * w + x)
                    if is_sentinel:
                        # Mark +/-1 king-move around the line tile
                        for adx in range(-1, 2):
                            for ady in range(-1, 2):
                                ax, ay = x + adx, y + ady
                                if (
                                    0 <= ax < w
                                    and 0 <= ay < h
                                    and (ax - tx) ** 2 + (ay - ty) ** 2 <= r_sq
                                ):
                                    state.danger_zones.add(ay * w + ax)
                    x += ddx
                    y += ddy

    # Also mark OUR gunners' firing lines as soft danger (avoid friendly fire)
    for ti in state.my_turrets:
        bld = state.building[ti]
        match bld:
            case BuildingGunner(direction=d, team=team) if team == state.my_team:
                tx, ty = ti % w, ti // w
                ddx, ddy = d.delta()
                x, y = tx + ddx, ty + ddy
                while 0 <= x < w and 0 <= y < h:
                    if (x - tx) ** 2 + (y - ty) ** 2 > 13:
                        break
                    state.danger_zones.add(y * w + x)
                    x += ddx
                    y += ddy


def _stamp_unit_tiles(state: State) -> None:
    w = state.w
    cost = state.cost
    for p in state.unit_tiles:
        cost[p.y * w + p.x] = COST_IMPASSABLE


def _update_connectivity(state: State) -> None:
    """BFS from core through friendly transport to find connected harvesters.

    A harvester is "connected" if there's a chain of friendly transport
    (conveyor/splitter/bridge) from it to the core. Topology only, no
    flow magnitudes. Capped at 256 iterations.
    """
    w, h = state.w, state.h
    my_team = state.my_team
    core_tiles = state.my_core_tiles
    transport = state.my_transport
    harvesters = state.my_harvesters

    if not harvesters:
        state.connected_harvesters.clear()
        return

    # BFS from core outward through friendly transport + check adjacent harvesters
    visited: set[int] = set(core_tiles)
    queue: deque[int] = deque(core_tiles)
    connected: set[int] = set()

    while queue:
        ci = queue.popleft()
        cx, cy = ci % w, ci // w
        for dx, dy in DIR4_DELTA:
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            ni = ny * w + nx
            if ni in visited:
                continue
            visited.add(ni)
            bld = state.building[ni]
            if bld is None or bld.team != my_team:
                continue
            if ni in transport:
                queue.append(ni)
            if ni in harvesters:
                connected.add(ni)

    state.connected_harvesters = connected


def _update_infra_staleness(state: State) -> None:
    """Track max staleness across our infrastructure tiles."""
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
