"""Vision scan, connectivity BFS, and capacity computation.

Per-turn update flow:
1. Vision scan → update env/building arrays, track sets
2. Connectivity BFS → connected_transport, connected_harvesters
3. Capacity trace → branch_load, bottleneck per tile
4. Tree validity → detect unexpected transport, invalidate branches
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from building import (
    ETYPE_BUILDING,
    Building,
    BuildingArmouredConveyor,
    BuildingBreach,
    BuildingBridge,
    BuildingConveyor,
    BuildingCore,
    BuildingGunner,
    BuildingHarvester,
    BuildingLauncher,
    BuildingMarker,
    BuildingSentinel,
    BuildingSplitter,
)
from cambc import Controller, EntityType, Environment
from marker import MarkerEureka
from marker import decode as decode_marker
from util import DIR4_DELTA, Symmetry

_FLOW_CHECK_TYPES = frozenset(
    {
        EntityType.CONVEYOR,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.SPLITTER,
        EntityType.BRIDGE,
    }
)

if TYPE_CHECKING:
    from state import State


def update(state: State, ct: Controller) -> None:
    """Main per-turn update."""
    state.age += 1
    state.pos = ct.get_position()

    _update_core_hp(state, ct)
    _update_ephemeral(state, ct)
    _scan_vision(state, ct)
    _decay_flow(state)
    _build_bridge_lookup(state)  # still needed for bridges_by_target
    # Connectivity + capacity now computed by FlowModel in builder.py
    _rebuild_danger_zones(state)


# ── Vision scan ──────────────────────────────────────────────


def _make_building(ct: Controller, bid: int, etype: EntityType) -> Building | None:
    team = ct.get_team(bid)
    match etype:
        case EntityType.CONVEYOR | EntityType.ARMOURED_CONVEYOR | EntityType.SPLITTER:
            return ETYPE_BUILDING[etype](team, ct.get_direction(bid))
        case EntityType.GUNNER | EntityType.SENTINEL | EntityType.BREACH:
            return ETYPE_BUILDING[etype](team, ct.get_direction(bid))
        case EntityType.BRIDGE:
            return BuildingBridge(team, ct.get_bridge_target(bid))
        case EntityType.MARKER:
            val = ct.get_marker_value(bid) if team == ct.get_team() else 0
            return BuildingMarker(team, val)
        case _:
            cls = ETYPE_BUILDING.get(etype)
            return cls(team) if cls is not None else None


def _update_core_hp(state: State, ct: Controller) -> None:
    core = state.core_pos
    if not ct.is_in_vision(core):
        return
    bid = ct.get_tile_building_id(core)
    if bid is not None:
        state.my_core_hp = ct.get_hp(bid)


def _update_ephemeral(state: State, ct: Controller) -> None:
    state.unit_tiles.clear()
    state.enemy_bots_nearby = False
    my_id = ct.get_id()
    my_team = state.my_team
    for uid in ct.get_nearby_units():
        if uid == my_id:
            continue
        state.unit_tiles.add(ct.get_position(uid))
        if ct.get_team(uid) != my_team:
            state.enemy_bots_nearby = True


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
        case (
            BuildingGunner()
            | BuildingSentinel()
            | BuildingBreach()
            | BuildingLauncher()
        ):
            return "turrets"
    return None


def _update_sets(
    state: State, idx: int, old_bld: Building | None, new_bld: Building | None
) -> None:
    my_team = state.my_team
    old_cat = _classify(old_bld)
    new_cat = _classify(new_bld)
    if old_cat == new_cat and (
        old_bld is None or new_bld is None or old_bld.team == new_bld.team
    ):
        return

    if old_cat is not None and old_bld is not None:
        prefix = "my_" if old_bld.team == my_team else "en_"
        getattr(state, prefix + old_cat).discard(idx)

    if new_cat is not None and new_bld is not None:
        prefix = "my_" if new_bld.team == my_team else "en_"
        getattr(state, prefix + new_cat).add(idx)


def _scan_vision(state: State, ct: Controller) -> None:
    w = state.w
    my_team = state.my_team
    rnd = ct.get_current_round()
    sym = state.symmetry
    scanned_flow: set[int] = set()

    for t in ct.get_nearby_tiles():
        i = t.y * w + t.x
        state.last_seen[i] = rnd

        env = ct.get_tile_env(t)
        old_env = state.env[i]
        if env != old_env:
            state.env[i] = env
            if env == Environment.ORE_TITANIUM:
                state.ore_ti.add(i)

        bid = ct.get_tile_building_id(t)
        old_bld = state.building[i]
        if bid is not None:
            etype = ct.get_entity_type(bid)
            bld = _make_building(ct, bid, etype)
            if bld != old_bld or env != old_env:
                state.building[i] = bld
                _update_sets(state, i, old_bld, bld)

                # Update passability grid
                if state.nav is not None:
                    is_allied = bld.team == my_team if bld is not None else False
                    state.nav.update_tile(i, env, etype, is_allied, sym)

            # Track flow: transport with stored resource
            if etype in _FLOW_CHECK_TYPES:
                res = ct.get_stored_resource(bid)
                if res is not None:
                    state.flow_seen[i] = 4
                    scanned_flow.add(i)

            match bld:
                case BuildingMarker(team=team) if team == my_team:
                    msg = decode_marker(bld.value)
                    match msg:
                        case MarkerEureka() if state.symmetry is None:
                            state.symmetry = Symmetry(msg.symmetry)
                case BuildingCore(team=team) if team != my_team:
                    state.en_core_tiles.add(i)
                    if state.en_core_pos is None:
                        state.en_core_pos = ct.get_position(bid)

        elif old_bld is not None or env != old_env:
            state.building[i] = None
            _update_sets(state, i, old_bld, None)
            if state.nav is not None:
                state.nav.update_tile(i, env, None, is_allied_building=False, sym=sym)

    state._scanned_flow = scanned_flow


def _decay_flow(state: State) -> None:
    """Decay flow_seen for tiles not refreshed this turn. Remove at 0."""
    scanned: set[int] = getattr(state, "_scanned_flow", set())
    to_remove: list[int] = []
    for ti, freshness in state.flow_seen.items():
        if ti in scanned:
            continue
        nf = freshness - 1
        if nf <= 0:
            to_remove.append(ti)
        else:
            state.flow_seen[ti] = nf
    for ti in to_remove:
        del state.flow_seen[ti]


def _build_bridge_lookup(state: State) -> None:
    """Build bridges_by_target: target_tile -> [bridge_tile, ...]."""
    w = state.w
    my_team = state.my_team
    lookup: dict[int, list[int]] = {}
    for bi in state.my_transport:
        bld = state.building[bi]
        if isinstance(bld, BuildingBridge) and bld.team == my_team:
            ti = bld.target.y * w + bld.target.x
            lookup.setdefault(ti, []).append(bi)
    state.bridges_by_target = lookup


# ── Connectivity + Capacity ──────────────────────────────────
#
# Single pass: direction-aware BFS from core, then load trace.
#
# Connectivity: BFS from core outward. A neighbor is connected if
# it has friendly transport/harvester that OUTPUTS toward the current
# tile. Bridges are handled inline (a bridge targeting a visited tile
# is itself visited, then BFS continues from it).
#
# Capacity: for each connected harvester, trace parent chain to core.
# Count load per tile, compute bottleneck (max load on path to core).

_TRANSPORT_TYPES = (
    BuildingConveyor,
    BuildingArmouredConveyor,
    BuildingSplitter,
    BuildingBridge,
)


def _outputs_toward(bld: Building, from_ti: int, to_ti: int, w: int) -> bool:
    """Does building at from_ti output toward to_ti?"""
    fx, fy = from_ti % w, from_ti // w
    tx, ty = to_ti % w, to_ti // w

    match bld:
        case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
            dx, dy = d.delta()
            return (fx + dx, fy + dy) == (tx, ty)
        case BuildingSplitter(direction=d):
            dx, dy = d.delta()
            for odx, ody in [(dx, dy), (-dy, dx), (dy, -dx)]:
                if (fx + odx, fy + ody) == (tx, ty):
                    return True
            return False
        case BuildingBridge(target=tgt):
            return (tgt.x, tgt.y) == (tx, ty)
        case BuildingHarvester():
            # Harvesters output to all adjacent cardinal tiles
            return abs(fx - tx) + abs(fy - ty) == 1
    return False


def _update_connectivity(state: State) -> None:
    """Direction-aware BFS from core. Builds parent map for capacity trace."""
    w, h = state.w, state.h
    my_team = state.my_team
    core_tiles = state.core_tiles
    transport = state.my_transport
    harvesters = state.my_harvesters
    building = state.building

    visited: set[int] = set(core_tiles)
    queue: deque[int] = deque(core_tiles)
    connected_transport: set[int] = set()
    connected_harvesters: set[int] = set()
    parent: dict[int, int] = {}

    while queue:
        ci = queue.popleft()
        cx, cy = ci % w, ci // w

        # Check cardinal neighbors
        for dx, dy in DIR4_DELTA:
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            ni = ny * w + nx
            if ni in visited:
                continue
            bld = building[ni]
            if bld is None or bld.team != my_team:
                continue
            if not _outputs_toward(bld, ni, ci, w):
                continue

            visited.add(ni)
            parent[ni] = ci
            if ni in transport:
                connected_transport.add(ni)
                queue.append(ni)
            elif ni in harvesters:
                connected_harvesters.add(ni)
                # Don't enqueue harvesters — they're leaves

        # Check for bridges targeting ci (O(1) lookup instead of r²≤9 scan)
        for bi in state.bridges_by_target.get(ci, []):
            if bi in visited:
                continue
            visited.add(bi)
            parent[bi] = ci
            connected_transport.add(bi)
            queue.append(bi)

    state.connected_transport = connected_transport
    state.connected_harvesters = connected_harvesters
    state._parent = parent


def _update_capacity(state: State) -> None:
    """Compute load and bottleneck from parent map.

    Load[tile] = number of connected harvesters whose path passes through tile.
    Bottleneck[tile] = max load on the path from tile to core (inclusive).
    """
    core_tiles = state.core_tiles
    parent = state._parent

    # 1. Trace each harvester to core, increment load along the way.
    #    Also count load on core tiles (total harvesters feeding through
    #    each core-adjacent transport into that core tile).
    load: dict[int, int] = {}
    for hi in state.connected_harvesters:
        current = parent.get(hi)
        seen: set[int] = set()
        while current is not None:
            if current in seen:
                break
            seen.add(current)
            load[current] = load.get(current, 0) + 1
            if current in core_tiles:
                break
            current = parent.get(current)

    # 2. Bottleneck: max load from tile to core.
    #    Compute top-down (from core outward) so each tile inherits
    #    its parent's bottleneck. Process in BFS order = parent always
    #    computed before children.
    #    Build child lists from parent map first.
    children: dict[int, list[int]] = {}
    for child, par in parent.items():
        children.setdefault(par, []).append(child)

    bottleneck: dict[int, int] = {}
    # Seed: core tiles have bottleneck = their own load (total harvesters
    # feeding through transport into this core tile).
    bfs_q: deque[int] = deque()
    for ct_tile in core_tiles:
        bottleneck[ct_tile] = load.get(ct_tile, 0)
        bfs_q.append(ct_tile)

    while bfs_q:
        ti = bfs_q.popleft()
        parent_bn = bottleneck[ti]
        for child in children.get(ti, []):
            child_load = load.get(child, 0)
            bottleneck[child] = max(parent_bn, child_load)
            bfs_q.append(child)

    state.load = load
    state.bottleneck = bottleneck
    state.branch_load = {}
    state.tile_branch = {}

    # Derive branch_load: group by the tile adjacent to core (branch root)
    for hi in state.connected_harvesters:
        current = parent.get(hi)
        prev = hi
        seen: set[int] = set()
        while current is not None and current not in core_tiles:
            if current in seen:
                break
            seen.add(current)
            prev = current
            current = parent.get(current)
        if current in core_tiles:
            # prev = the transport tile adjacent to core = branch root
            state.tile_branch[hi] = prev
            state.branch_load[prev] = state.branch_load.get(prev, 0) + 1


def _is_branch_trusted(state: State, ti: int) -> bool:
    """Walk from ti to core via parent. Untrusted if any tile on path was never seen."""
    parent = state._parent
    core_tiles = state.core_tiles
    current = ti
    seen: set[int] = set()
    while current is not None and current not in core_tiles:
        if current in seen:
            return False  # cycle
        seen.add(current)
        if state.last_seen[current] == 0:
            return False
        current = parent.get(current)
    return True


# ── Danger zones ─────────────────────────────────────────────


def _rebuild_danger_zones(state: State) -> None:
    w, h = state.w, state.h
    state.danger_zones = set()

    for ti in state.en_turrets:
        bld = state.building[ti]
        tx, ty = ti % w, ti // w

        match bld:
            case BuildingLauncher():
                # Launcher pickup r²=2 — hard block nav + danger zones
                nav = state.nav
                for dx in range(-2, 3):
                    for dy in range(-2, 3):
                        if dx * dx + dy * dy > 2:
                            continue
                        nx, ny = tx + dx, ty + dy
                        if 0 <= nx < w and 0 <= ny < h:
                            ni = ny * w + nx
                            state.danger_zones.add(ni)
                            if nav is not None:
                                nav.set_passable_at(ni, passable=False)

            case (
                BuildingGunner(direction=d)
                | BuildingSentinel(direction=d)
                | BuildingBreach(direction=d)
            ):
                ddx, ddy = d.delta()
                r_sq = 13 if isinstance(bld, (BuildingGunner, BuildingBreach)) else 32
                x, y = tx + ddx, ty + ddy
                while 0 <= x < w and 0 <= y < h:
                    if (x - tx) ** 2 + (y - ty) ** 2 > r_sq:
                        break
                    state.danger_zones.add(y * w + x)
                    x += ddx
                    y += ddy
