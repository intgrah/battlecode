"""Builder helper functions and constants.

Pure functions that operate on State/NavBfs/Controller — no Builder dependency.
This is the leaf of the builder_* import DAG.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    CHEAP_DESTROYABLE,
    TI_CONSUMERS,
    TRANSPORT,
    TURRETS,
    BuildingArmouredConveyor,
    BuildingBarrier,
    BuildingBridge,
    BuildingConveyor,
    BuildingFoundry,
    BuildingGunner,
    BuildingHarvester,
    BuildingLauncher,
    BuildingMarker,
    BuildingRoad,
    BuildingSentinel,
    BuildingSplitter,
)
from cambc import Controller, Direction, EntityType, Environment, Position
from util import DELTA_TO_DIR, DIR4_DELTA, DIR8_DELTA

if TYPE_CHECKING:
    from nav import NavBfs
    from reachable import Reachable
    from state import State
    from tracker import Tracker
    from util import Symmetry

# ── Constants ───────────────────────────────────────────────

# Max harvesters per branch (4 = true throughput limit, 1 stack/turn)
_BRANCH_CAPACITY = 4

# Tile cache keys (avoid recreating dicts every turn)
_ENV_INT: dict[Environment, int] = {e: i for i, e in enumerate(Environment)}
_ET_INT: dict[EntityType, int] = {e: i + 1 for i, e in enumerate(EntityType)}

_UNBUILDABLE_ENV = frozenset({Environment.WALL})

# Precomputed valid offsets for turret targeting (hardcoded)
# Gunner: on cardinal/diagonal ray, r2<=13
_GUNNER_OFFSETS: frozenset[tuple[int, int]] = frozenset(
    {
        (-3, 0),
        (-2, -2),
        (-2, 0),
        (-2, 2),
        (-1, -1),
        (-1, 0),
        (-1, 1),
        (0, -3),
        (0, -2),
        (0, -1),
        (0, 1),
        (0, 2),
        (0, 3),
        (1, -1),
        (1, 0),
        (1, 1),
        (2, -2),
        (2, 0),
        (2, 2),
        (3, 0),
    }
)

# Sentinel: Chebyshev <=1 from any cardinal/diagonal ray tile, r2<=32
_SENTINEL_OFFSETS: frozenset[tuple[int, int]] = frozenset(
    {
        (-5, -1),
        (-5, 0),
        (-5, 1),
        (-4, -4),
        (-4, -3),
        (-4, -2),
        (-4, -1),
        (-4, 0),
        (-4, 1),
        (-4, 2),
        (-4, 3),
        (-4, 4),
        (-3, -4),
        (-3, -3),
        (-3, -2),
        (-3, -1),
        (-3, 0),
        (-3, 1),
        (-3, 2),
        (-3, 3),
        (-3, 4),
        (-2, -4),
        (-2, -3),
        (-2, -2),
        (-2, -1),
        (-2, 0),
        (-2, 1),
        (-2, 2),
        (-2, 3),
        (-2, 4),
        (-1, -5),
        (-1, -4),
        (-1, -3),
        (-1, -2),
        (-1, -1),
        (-1, 0),
        (-1, 1),
        (-1, 2),
        (-1, 3),
        (-1, 4),
        (-1, 5),
        (0, -5),
        (0, -4),
        (0, -3),
        (0, -2),
        (0, -1),
        (0, 1),
        (0, 2),
        (0, 3),
        (0, 4),
        (0, 5),
        (1, -5),
        (1, -4),
        (1, -3),
        (1, -2),
        (1, -1),
        (1, 0),
        (1, 1),
        (1, 2),
        (1, 3),
        (1, 4),
        (1, 5),
        (2, -4),
        (2, -3),
        (2, -2),
        (2, -1),
        (2, 0),
        (2, 1),
        (2, 2),
        (2, 3),
        (2, 4),
        (3, -4),
        (3, -3),
        (3, -2),
        (3, -1),
        (3, 0),
        (3, 1),
        (3, 2),
        (3, 3),
        (3, 4),
        (4, -4),
        (4, -3),
        (4, -2),
        (4, -1),
        (4, 0),
        (4, 1),
        (4, 2),
        (4, 3),
        (4, 4),
        (5, -1),
        (5, 0),
        (5, 1),
    }
)


# ── Helper functions ────────────────────────────────────────


DEBUG = False


def _log(msg: str, _bot_id: int = 0) -> None:
    if DEBUG:
        import sys  # noqa: PLC0415

        print(msg)
        sys.stderr.write(f"[B{_bot_id}] {msg}\n")


def _find_core(ct: Controller) -> Position:
    my = ct.get_team()
    for bid in ct.get_nearby_buildings():
        if ct.get_team(bid) == my and ct.get_entity_type(bid) == EntityType.CORE:
            return ct.get_position(bid)
    return ct.get_position()


def _destroy_friendly(
    ct: Controller, pos: Position, *, allow_barrier: bool = False
) -> None:
    """Destroy own road/marker (and optionally barrier) at pos."""
    bid = ct.get_tile_building_id(pos)
    if bid is None:
        return
    if ct.get_team(bid) != ct.get_team():
        return
    etype = ct.get_entity_type(bid)
    if etype in (EntityType.ROAD, EntityType.MARKER):
        if ct.can_destroy(pos):
            ct.destroy(pos)
    elif allow_barrier and etype == EntityType.BARRIER and ct.can_destroy(pos):
        ct.destroy(pos)


def _feeds_enemy(s: State, si: int) -> bool:
    """Check if our transport at si outputs to enemy transport/turret/core.

    Only flags buildings that actually consume or route our Ti:
    - Enemy transport (conveyor/splitter/bridge) → routes Ti to enemy
    - Enemy turrets (gunner/sentinel/breach) → uses Ti as ammo
    - Enemy core → collects Ti

    Does NOT flag: roads, barriers, harvesters, markers, foundries —
    these don't steal our resources.
    """
    bld = s.building[si]
    if bld is None or bld.team != s.my_team:
        return False
    w = s.w
    sx, sy = si % w, si // w

    out_tiles: list[tuple[int, int]] = []
    match bld:
        case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
            ddx, ddy = d.delta()
            out_tiles.append((sx + ddx, sy + ddy))
        case BuildingSplitter(direction=d):
            ddx, ddy = d.delta()
            for odx, ody in [(ddx, ddy), (-ddy, ddx), (ddy, -ddx)]:
                out_tiles.append((sx + odx, sy + ody))
        case BuildingBridge(target=tgt):
            out_tiles.append((tgt.x, tgt.y))
        case _:
            return False

    for ox, oy in out_tiles:
        if not s.in_bounds(ox, oy):
            continue
        oi = oy * w + ox
        out_bld = s.building[oi]
        if out_bld is None or out_bld.team == s.my_team:
            continue
        # Only flag buildings that actually route or consume our Ti
        if isinstance(out_bld, TI_CONSUMERS):
            return True
    return False


def _has_nearby_threat(s: State, tile_idx: int) -> bool:
    """Check if any enemy turret is within Manhattan distance 5 of a tile."""
    w = s.w
    tx, ty = tile_idx % w, tile_idx // w
    for eti in s.en_turrets:
        ex, ey = eti % w, eti // w
        if abs(ex - tx) + abs(ey - ty) <= 5:
            return True
    return False


def _tile_has_correct_transport(s: State, ci: int, ni: int, w: int) -> bool:
    """Check if tile ci already has transport outputting toward ni.

    Uses flow model if available, falls back to manual check.
    """
    if ci in s.core_tiles:
        return True
    bld = s.building[ci]
    if isinstance(bld, BuildingHarvester):
        return True
    if bld is None:
        return False
    if bld.team != s.my_team:
        return False

    # Use flow model (single source of truth for outputs)
    flow = getattr(s, 'flow', None)
    if flow is not None:
        return ni in flow.outputs_of(ci)

    # Fallback (before flow model is built, e.g. first turn)
    cx, cy = ci % w, ci // w
    nx, ny = ni % w, ni // w
    match bld:
        case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
            ddx, ddy = d.delta()
            return (cx + ddx, cy + ddy) == (nx, ny)
        case BuildingSplitter(direction=d):
            ddx, ddy = d.delta()
            for odx, ody in [(ddx, ddy), (-ddy, ddx), (ddy, -ddx)]:
                if (cx + odx, cy + ody) == (nx, ny):
                    return True
            return False
        case BuildingBridge(target=tgt):
            return (tgt.x, tgt.y) == (nx, ny)
        case BuildingFoundry():
            return True
    return False


def _has_los(s: State, gx: int, gy: int, fdx: int, fdy: int) -> int | None:
    """Walk ray from gunner position, return first enemy building tile or None.

    For PLANNING purposes (not game simulation):
    - Walls: block LoS → return None
    - Markers: don't block → skip
    - Our roads: don't block → skip (gunner destroys them in 1-2 shots)
    - Other friendly buildings: block → return None
    - Enemy buildings: target → return tile
    """
    w, h = s.w, s.h
    my_team = s.my_team
    x, y = gx + fdx, gy + fdy
    while 0 <= x < w and 0 <= y < h:
        if (x - gx) ** 2 + (y - gy) ** 2 > 13:
            break
        ni = y * w + x
        env = s.env[ni]
        if env == Environment.WALL:
            return None
        bld = s.building[ni]
        if bld is not None and not isinstance(bld, BuildingMarker):
            if bld.team != my_team:
                return ni  # enemy target
            # Our road: gunner shoots through it (5 HP, 1-2 shots) → skip
            if isinstance(bld, BuildingRoad):
                x += fdx
                y += fdy
                continue
            return None  # other friendly building blocks
        x += fdx
        y += fdy
    return None


def _has_friendly_gunner_covering(s: State, threat_ti: int) -> bool:
    """Check if we already have a friendly gunner within r²=13 of the threat."""
    w = s.w
    tx, ty = threat_ti % w, threat_ti // w
    for dx in range(-4, 5):
        for dy in range(-4, 5):
            if dx * dx + dy * dy > 13:
                continue
            gx, gy = tx + dx, ty + dy
            if not s.in_bounds(gx, gy):
                continue
            bld = s.building[gy * w + gx]
            if isinstance(bld, BuildingGunner) and bld.team == s.my_team:
                return True
    return False


def _update_nearby_tiles(
    nav: NavBfs,
    ti_ore: Tracker,
    state: State,
    ct: Controller,
    tile_cache: bytearray,
    sym: Symmetry | None,
    reachable: Reachable | None = None,
) -> None:
    """Read nearby tiles and update nav grid + ore tracker + reachability."""
    w = state.w
    my_team = ct.get_team()

    env_int = _ENV_INT
    et_int = _ET_INT

    for tile in ct.get_nearby_tiles():
        i = tile.y * w + tile.x
        env = ct.get_tile_env(tile)
        bid = ct.get_tile_building_id(tile)
        building_type = ct.get_entity_type(bid) if bid is not None else None
        is_allied = bid is not None and ct.get_team(bid) == my_team

        bt = et_int.get(building_type, 0) if building_type is not None else 0
        key = env_int.get(env, 0) | (bt << 2) | (int(is_allied) << 6)
        if tile_cache[i] == key:
            continue
        tile_cache[i] = key

        nav.update_tile(i, env, building_type, is_allied, sym)
        ti_ore.update_tile(i, env, sym)
        if reachable is not None:
            reachable.update_tile(i, env)


def _can_place_gunner(s: State, gi: int, *, check_danger: bool = True) -> bool:
    """Check if tile is valid for gunner placement.

    Only approves own buildings we can actually clear (roads, markers,
    barriers, non-econ transport).  Harvesters/turrets/core are off-limits.
    Ore tiles are fine (gunners can be built on ore). Only walls are blocked.
    """
    env = s.env[gi]
    if env == Environment.WALL:
        return False
    if check_danger and gi in s.danger_zones:
        return False
    bld = s.building[gi]
    if bld is not None:
        if isinstance(bld, BuildingMarker):
            return True
        if bld.team == s.my_team:
            if isinstance(bld, CHEAP_DESTROYABLE):
                return True
            if isinstance(bld, TRANSPORT):
                return gi not in s.connected_transport
            return False  # harvester, turret, core
        return False  # enemy building
    return True


def _can_place_gunner_at(s: State, gi: int) -> bool:
    """Check if tile is valid for gunner placement (defense, no danger check)."""
    return _can_place_gunner(s, gi, check_danger=False)


def _clear_tile(ct: Controller, s: State, ti: int, pos: Position) -> None:
    """Destroy own building at tile to make room. Skips connected transport."""
    if ti in s.connected_transport:
        return
    bid = ct.get_tile_building_id(pos)
    if bid is None:
        return
    if ct.get_team(bid) != ct.get_team():
        return
    etype = ct.get_entity_type(bid)
    if etype in (
        EntityType.ROAD,
        EntityType.MARKER,
        EntityType.BARRIER,
        EntityType.CONVEYOR,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.SPLITTER,
        EntityType.BRIDGE,
    ) and ct.can_destroy(pos):
        ct.destroy(pos)
        s.building[ti] = None
        s.my_transport.discard(ti)


def _task_destroy_enemy_infra(
    s: State, nav: NavBfs, ct: Controller
) -> tuple[str, bool] | None:
    """Walk to and fire at enemy transport or harvester-adjacent buildings."""
    w = s.w
    pos = ct.get_position()
    my_team = s.my_team

    # Already on an enemy building? Fire — but only at transport/harvesters, not roads.
    if ct.get_action_cooldown() == 0:
        bid = ct.get_tile_building_id(pos)
        if bid is not None and ct.get_team(bid) != my_team:
            etype = ct.get_entity_type(bid)
            if etype not in (EntityType.ROAD, EntityType.MARKER) and ct.can_fire(pos):
                ct.fire(pos)
                return "destroy_enemy:fire", True

    # Target: enemy transport tiles — skip tiles in danger zones
    best_pos: Position | None = None
    best_dist = 1_000_000
    for ti in s.en_transport:
        if ti in s.danger_zones:
            continue
        tx, ty = ti % w, ti // w
        d = abs(pos.x - tx) + abs(pos.y - ty)
        if d < best_dist:
            best_dist = d
            best_pos = Position(tx, ty)

    if best_pos is None or best_dist > 5:
        return None

    nav.set_goal(best_pos)
    moved = nav.step(ct)
    return f"destroy_enemy:walk({best_pos.x},{best_pos.y})", moved


def _task_cut_feed(s: State, nav: NavBfs, ct: Controller) -> tuple[str, bool] | None:
    """Cut our cheap transport that outputs to enemy buildings."""
    w = s.w
    pos = ct.get_position()

    for bid in ct.get_nearby_buildings():
        if ct.get_team(bid) != s.my_team:
            continue
        etype = ct.get_entity_type(bid)
        # Only cut cheap transport -- harvesters are too expensive to replace
        if etype not in (
            EntityType.CONVEYOR,
            EntityType.ARMOURED_CONVEYOR,
            EntityType.SPLITTER,
            EntityType.BRIDGE,
        ):
            continue
        bpos = ct.get_position(bid)
        si = bpos.y * w + bpos.x
        if not _feeds_enemy(s, si):
            continue

        feed_pos = Position(bpos.x, bpos.y)
        if pos.distance_squared(feed_pos) <= 2 and ct.can_destroy(feed_pos):
            ct.destroy(feed_pos)
            s.building[si] = None
            s.my_transport.discard(si)
            s.connected_transport.discard(si)
            # Barrier to prevent enemy from using this tile
            if ct.can_build_barrier(feed_pos):
                ct.build_barrier(feed_pos)
                s.building[si] = BuildingBarrier(s.my_team)
            return f"cut_feed:intercept({bpos.x},{bpos.y})", True
        nav.set_goal(feed_pos)
        moved = nav.step(ct)
        return f"cut_feed:walk({bpos.x},{bpos.y})", moved

    return None


# ── Unified turret placement ───────────────────────────────

_TRANSPORT_OR_TURRETS = TRANSPORT + TURRETS

# Valid turret targets: core + turrets (not launcher, not harvester, not transport)
_TURRET_SKIP = (BuildingRoad, BuildingMarker, BuildingHarvester, BuildingLauncher)


def _in_sentinel_arc(
    sx: int, sy: int, fdx: int, fdy: int, tx: int, ty: int
) -> bool:
    """Check if target is in sentinel arc: within Chebyshev 1 of facing ray, r²≤32."""
    if (tx - sx) ** 2 + (ty - sy) ** 2 > 32:
        return False
    rx, ry = sx + fdx, sy + fdy
    while (rx - sx) ** 2 + (ry - sy) ** 2 <= 32:
        if max(abs(tx - rx), abs(ty - ry)) <= 1:
            return True
        rx += fdx
        ry += fdy
    return False


def try_place_turret_at(
    s: State,
    ct: Controller,
    nav: NavBfs,
    ti: int,
    feed_ti: int | None,
    pos: Position,
    *,
    max_walk: int = 5,
    gunner_only: bool = False,
    sentinel_only: bool = False,
) -> tuple[str, bool] | None:
    """Unified turret placement. Tries gunner first, sentinel fallback.

    Returns action tuple if turret placed/walking/waiting, None if can't place.
    Used by attack (chain extension) and defense (reactive gunner).
    """
    w = s.w
    tx, ty = ti % w, ti // w
    tpos = Position(tx, ty)

    # ── Placement checks ──
    if not _can_place_gunner(s, ti, check_danger=False):
        return None
    if ti in s.my_transport:
        return None
    bld = s.building[ti]
    if bld is not None and bld.team == s.my_team and isinstance(bld, _TRANSPORT_OR_TURRETS):
        return None
    if not nav.is_passable(tpos):
        return None
    if abs(pos.x - tx) + abs(pos.y - ty) > max_walk:
        return None

    # ── Feed direction (turret can't face toward feeder) ──
    if feed_ti is None:
        feed_dx, feed_dy = 99, 99  # no constraint
    else:
        px, py = feed_ti % w, feed_ti // w
        dx_raw, dy_raw = px - tx, py - ty
        # Bridge hop (non-cardinal) → turret can face any direction
        if abs(dx_raw) > 1 or abs(dy_raw) > 1 or (dx_raw != 0 and dy_raw != 0):
            feed_dx, feed_dy = 99, 99
        else:
            feed_dx = 1 if dx_raw > 0 else (-1 if dx_raw < 0 else 0)
            feed_dy = 1 if dy_raw > 0 else (-1 if dy_raw < 0 else 0)

    # ── Valid targets: core + turrets (not launcher), recently seen ──
    rnd = s.age + s.birthday
    en_targets = s.en_core_tiles | s.en_turrets
    # Filter out launchers
    en_targets = {
        e for e in en_targets
        if not isinstance(s.building[e], BuildingLauncher)
        and rnd - s.last_seen[e] <= 20
    }

    # ── Gunner: 8-direction LoS scan ──
    if not sentinel_only:
        for fdx, fdy in DIR8_DELTA:
            if (fdx, fdy) == (feed_dx, feed_dy):
                continue
            hit = _has_los(s, tx, ty, fdx, fdy)
            if hit is None:
                continue
            hit_bld = s.building[hit]
            if hit_bld is None or hit_bld.team == s.my_team:
                continue
            if isinstance(hit_bld, _TURRET_SKIP):
                continue
            # Any non-skipped enemy building in LoS is a valid target
            facing = DELTA_TO_DIR.get((fdx, fdy))
            if facing is None:
                continue
            # VERIFY FEED before committing (the key invariant)
            flow = getattr(s, 'flow', None)
            if flow is not None and not flow.has_feed_for_turret(ti, fdx, fdy):
                continue  # no verified feed — skip this direction
            hx, hy = hit % w, hit // w
            _log(f"  turret({tx},{ty}): gunner face={facing.name} -> ({hx},{hy})", ct.get_id())
            return _do_place(s, ct, nav, ti, tpos, pos, facing, sentinel=False)

    if gunner_only:
        return None

    # ── Sentinel: r²≤32 arc scan ──
    for eti in en_targets:
        ebld = s.building[eti]
        if ebld is None or ebld.team == s.my_team:
            continue
        if isinstance(ebld, _TURRET_SKIP):
            continue
        ex, ey = eti % w, eti // w
        if (ex - tx) ** 2 + (ey - ty) ** 2 > 32:
            continue
        for fdx, fdy in DIR8_DELTA:
            if (fdx, fdy) == (feed_dx, feed_dy):
                continue
            if _in_sentinel_arc(tx, ty, fdx, fdy, ex, ey):
                facing = DELTA_TO_DIR.get((fdx, fdy))
                if facing is None:
                    continue
                # VERIFY FEED
                flow = getattr(s, 'flow', None)
                if flow is not None and not flow.has_feed_for_turret(ti, fdx, fdy):
                    continue
                _log(f"  turret({tx},{ty}): sentinel face={facing.name} -> ({ex},{ey})", ct.get_id())
                return _do_place(s, ct, nav, ti, tpos, pos, facing, sentinel=True)

    return None


def _do_place(
    s: State,
    ct: Controller,
    nav: NavBfs,
    ti: int,
    tpos: Position,
    pos: Position,
    facing: Direction,
    *,
    sentinel: bool,
) -> tuple[str, bool] | None:
    """Physical turret placement: stepoff, walk, wait for bot, verify, build."""
    w = s.w
    tx, ty = ti % w, ti // w

    # Bot on tile — can't place turret, wait
    if tpos in s.unit_tiles:
        return f"turret:wait_bot({tx},{ty})", False

    # Step off
    if pos == tpos:
        for d in Direction:
            if d != Direction.CENTRE and ct.can_move(d):
                ct.move(d)
                return f"turret:stepoff({tx},{ty})", True
        return f"turret:trapped({tx},{ty})", False

    # Walk closer
    if pos.distance_squared(tpos) > 2:
        nav.set_goal(tpos)
        return f"turret:walk({tx},{ty})", nav.step(ct)

    # Resource check
    cost, _ = ct.get_sentinel_cost() if sentinel else ct.get_gunner_cost()
    ti_res, _ = ct.get_global_resources()
    if ti_res < cost:
        return "turret:wait_ti", False

    # Re-verify target still exists
    fdx, fdy = facing.delta()
    rnd = s.age + s.birthday
    en_targets = s.en_core_tiles | s.en_turrets
    en_targets = {
        e for e in en_targets
        if not isinstance(s.building[e], BuildingLauncher)
        and rnd - s.last_seen[e] <= 20
    }

    has_target = False
    if sentinel:
        for eti in en_targets:
            ebld = s.building[eti]
            if ebld is None or isinstance(ebld, _TURRET_SKIP):
                continue
            ex, ey = eti % w, eti // w
            if _in_sentinel_arc(tx, ty, fdx, fdy, ex, ey):
                has_target = True
                break
    else:
        hit = _has_los(s, tx, ty, fdx, fdy)
        if hit is not None:
            hbld = s.building[hit]
            if hbld is not None and hbld.team != s.my_team and not isinstance(hbld, _TURRET_SKIP):
                has_target = True

    if not has_target:
        _log(f"  turret({tx},{ty}): target_gone", ct.get_id())
        return None

    # Build
    _clear_tile(ct, s, ti, tpos)
    kind = "sentinel" if sentinel else "gunner"
    if sentinel:
        if ct.can_build_sentinel(tpos, facing):
            ct.build_sentinel(tpos, facing)
            s.building[ti] = BuildingSentinel(s.my_team, facing)
            _log(f"  PLACED {kind}({tx},{ty}) face={facing.name}", ct.get_id())
            return f"turret:{kind}({tx},{ty})", True
    else:
        if ct.can_build_gunner(tpos, facing):
            ct.build_gunner(tpos, facing)
            s.building[ti] = BuildingGunner(s.my_team, facing)
            _log(f"  PLACED {kind}({tx},{ty}) face={facing.name}", ct.get_id())
            return f"turret:{kind}({tx},{ty})", True

    return None

    return None
