"""Defense role: reactive gunner, heal, barrier, patrol, intercept raiders."""

from __future__ import annotations

from typing import TYPE_CHECKING

from builder_econ import _task_connect, _task_explore
from builder_helpers import (
    _can_place_gunner_at,
    _clear_tile,
    _destroy_friendly,
    _has_friendly_gunner_covering,
    _has_los,
    _log,
    _task_destroy_enemy_infra,
    _tile_has_correct_transport,
)
from building import (
    BuildingGunner,
    BuildingHarvester,
    BuildingLauncher,
    BuildingMarker,
    BuildingRoad,
)
from cambc import Controller, Direction, EntityType, Environment, Position
from util import DELTA_TO_DIR, DIR4_DELTA

if TYPE_CHECKING:
    from builder import Builder
    from state import State


def _run_defense(builder: Builder, ct: Controller) -> tuple[str, bool]:

    # 1. Intercept enemy raiders attacking our infrastructure
    result = _task_intercept_raider(builder, ct)
    if result is not None:
        return result

    # 2. Reactive gunner against enemy turret in our base
    result = _task_reactive_gunner(builder, ct)
    if result is not None:
        return result

    # 3. Repair broken chains
    result = _task_repair_chain(builder, ct)
    if result is not None:
        return result

    # 4. Heal damaged infra
    result = _task_heal_infra(builder, ct)
    if result is not None:
        return result

    # 5. Barrier harvesters
    result = _task_barrier_harvesters(builder, ct)
    if result is not None:
        return result

    # 6. Destroy nearby enemy infra (low priority for defense)
    result = _task_destroy_enemy_infra(builder.state, builder.nav, ct)
    if result is not None:
        return result

    # 7. Patrol
    return _task_patrol(builder, ct)


def _ray_clear_to(
    s: State, gx: int, gy: int, fdx: int, fdy: int, tx: int, ty: int
) -> bool:
    """Check if a gunner ray from (gx,gy) in direction (fdx,fdy) reaches (tx,ty).

    Returns True if the ray can reach the target tile without being blocked
    by walls or friendly buildings. Enemy buildings/bots on the way are fine
    (they're targetable and the gunner will shoot them).
    """
    w, h = s.w, s.h
    my_team = s.my_team
    x, y = gx + fdx, gy + fdy
    while 0 <= x < w and 0 <= y < h:
        if (x - gx) ** 2 + (y - gy) ** 2 > 13:
            break
        if x == tx and y == ty:
            return True  # reached the target tile
        ni = y * w + x
        env = s.env[ni]
        if env == Environment.WALL:
            return False
        bld = s.building[ni]
        if bld is not None and not isinstance(bld, BuildingMarker):
            if bld.team == my_team:
                return False  # own building blocks
            # Enemy building: targetable, blocks further ray — target must be here
            return x == tx and y == ty
        x += fdx
        y += fdy
    return False


def _task_intercept_raider(builder: Builder, ct: Controller) -> tuple[str, bool] | None:
    """Place a gunner to kill enemy builder bots attacking our infrastructure.

    Triggers when an enemy builder bot is near our buildings (within Manhattan
    distance 2). Searches for any buildable tile within gunner range (r²≤13)
    of the raider that has a friendly transport or harvester on a non-facing
    side to feed ammo. Does NOT require connected transport or active flow —
    even a disconnected conveyor with stored resources works.
    """
    s = builder.state
    w = s.w
    pos = ct.get_position()
    my_team = s.my_team

    if ct.get_action_cooldown() != 0:
        return None

    g_cost, _ = ct.get_gunner_cost()
    ti_res, _ = ct.get_global_resources()
    if ti_res < g_cost:
        return None

    # Find enemy builder bots near our buildings (not just standing ON them)
    raider_positions: list[Position] = []
    for uid in ct.get_nearby_units():
        if ct.get_team(uid) == my_team:
            continue
        if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
            continue
        epos = ct.get_position(uid)
        ex, ey = epos.x, epos.y
        # Check if enemy bot is near any of our non-trivial buildings
        near_our_stuff = False
        for ddx in range(-2, 3):
            for ddy in range(-2, 3):
                ax, ay = ex + ddx, ey + ddy
                if not s.in_bounds(ax, ay):
                    continue
                ai = ay * w + ax
                abld = s.building[ai]
                if abld is None or abld.team != my_team:
                    continue
                if isinstance(abld, (BuildingMarker, BuildingRoad)):
                    continue
                near_our_stuff = True
                break
            if near_our_stuff:
                break
        if near_our_stuff:
            raider_positions.append(epos)

    if not raider_positions:
        return None

    # Filter out raiders already covered by a friendly gunner
    uncovered: list[Position] = []
    for epos in raider_positions:
        eti = epos.y * w + epos.x
        if not _has_friendly_gunner_covering(s, eti):
            uncovered.append(epos)
    raider_positions = uncovered

    if not raider_positions:
        return None

    # Search for any buildable tile within gunner range that has a friendly
    # transport/harvester on a non-facing side for ammo feed.
    best_gpos: Position | None = None
    best_facing: Direction | None = None
    best_gdist = 1_000_000

    # Collect all friendly transport + harvester tiles as potential feeders
    feeder_tiles: set[int] = s.my_transport | s.my_harvesters

    for epos in raider_positions:
        ex, ey = epos.x, epos.y
        # Search tiles within gunner range of the raider
        for gdx in range(-3, 4):
            for gdy in range(-3, 4):
                if gdx * gdx + gdy * gdy > 13:
                    continue
                if gdx == 0 and gdy == 0:
                    continue
                gx, gy = ex + gdx, ey + gdy
                if not s.in_bounds(gx, gy):
                    continue
                gi = gy * w + gx
                if not _can_place_gunner_at(s, gi):
                    continue
                # Compute facing toward raider
                fdx = 0 if ex == gx else (1 if ex > gx else -1)
                fdy = 0 if ey == gy else (1 if ey > gy else -1)
                if fdx == 0 and fdy == 0:
                    continue
                facing = DELTA_TO_DIR.get((fdx, fdy))
                if facing is None:
                    continue
                # Check non-facing cardinal sides for any friendly feeder
                has_feed = False
                for adx, ady in DIR4_DELTA:
                    if (adx, ady) == (fdx, fdy):
                        continue  # facing side — can't receive ammo
                    fax, fay = gx + adx, gy + ady
                    if not s.in_bounds(fax, fay):
                        continue
                    fai = fay * w + fax
                    if fai not in feeder_tiles:
                        continue
                    fbld = s.building[fai]
                    if fbld is None or fbld.team != my_team:
                        continue
                    # Harvester outputs all cardinal — always valid
                    if isinstance(fbld, BuildingHarvester):
                        has_feed = True
                        break
                    # Transport: must output toward gunner tile
                    if _tile_has_correct_transport(s, fai, gi, w):
                        has_feed = True
                        break
                if not has_feed:
                    continue
                # Verify LoS to raider
                if not _ray_clear_to(s, gx, gy, fdx, fdy, ex, ey):
                    continue
                d = abs(pos.x - gx) + abs(pos.y - gy)
                if d < best_gdist:
                    best_gdist = d
                    best_gpos = Position(gx, gy)
                    best_facing = facing

    if best_gpos is None or best_facing is None:
        return None

    gi = best_gpos.y * w + best_gpos.x

    # Walk to the tile if not adjacent
    if pos.distance_squared(best_gpos) > 2:
        builder.nav.set_goal(best_gpos)
        moved = builder.nav.step(ct)
        return f"def:intercept_walk({best_gpos.x},{best_gpos.y})", moved

    # Step off if standing on it
    if pos == best_gpos:
        for d in Direction:
            if d != Direction.CENTRE and ct.can_move(d):
                ct.move(d)
                return "def:intercept_stepoff", True
        return None

    # Clear road/marker/barrier if present
    _clear_tile(ct, s, gi, best_gpos)

    if ct.can_build_gunner(best_gpos, best_facing):
        ct.build_gunner(best_gpos, best_facing)
        s.building[gi] = BuildingGunner(s.my_team, best_facing)
        s.my_turrets.add(gi)
        return f"def:intercept_gunner({best_gpos.x},{best_gpos.y})", True

    return None


def _task_reactive_gunner(builder: Builder, ct: Controller) -> tuple[str, bool] | None:
    """Place gunner near enemy turret using local flow."""
    s = builder.state
    w = s.w
    pos = ct.get_position()

    # Find uncovered enemy turrets (not launchers)
    threats: list[int] = []
    for ti in s.en_turrets:
        if isinstance(s.building[ti], BuildingLauncher):
            continue
        if not _has_friendly_gunner_covering(s, ti):
            threats.append(ti)

    if not threats:
        return None

    # Pick closest threat
    best_ti: int | None = None
    best_d = 1_000_000
    for ti in threats:
        tx, ty = ti % w, ti // w
        d = abs(pos.x - tx) + abs(pos.y - ty)
        if d < best_d:
            best_d = d
            best_ti = ti

    if best_ti is None:
        return None

    ttx, tty = best_ti % w, best_ti // w

    g_cost, _ = ct.get_gunner_cost()
    ti_res, _ = ct.get_global_resources()
    if ti_res < g_cost:
        return None

    # Search expanding ring around threat for valid gunner placement.
    # Valid = placeable tile + LoS to threat + adjacent harvester/connected transport
    # on a non-facing side (for ammo feed).
    _log(f"  reactive_gunner: threat=({ttx},{tty})", ct.get_id())
    best_gpos: Position | None = None
    best_facing: Direction | None = None
    best_gdist = 1_000_000
    for r in range(1, 5):
        for gdx in range(-r, r + 1):
            for gdy in range(-r, r + 1):
                if abs(gdx) != r and abs(gdy) != r:
                    continue  # ring edge only
                gx, gy = ttx + gdx, tty + gdy
                if not s.in_bounds(gx, gy):
                    continue
                gi = gy * w + gx
                if not _can_place_gunner_at(s, gi):
                    bld = s.building[gi]
                    env = s.env[gi]
                    reason = (
                        env.name
                        if env
                        and env
                        in (
                            Environment.WALL,
                            Environment.ORE_TITANIUM,
                            Environment.ORE_AXIONITE,
                        )
                        else (type(bld).__name__[8:] if bld else "?")
                    )
                    _log(f"    ({gx},{gy}) cant_place: {reason}", ct.get_id())
                    continue
                fdx = 0 if ttx == gx else (1 if ttx > gx else -1)
                fdy = 0 if tty == gy else (1 if tty > gy else -1)
                if fdx == 0 and fdy == 0:
                    continue
                if _has_los(s, gx, gy, fdx, fdy) is None:
                    _log(f"    ({gx},{gy}) no_los face=({fdx},{fdy})", ct.get_id())
                    continue
                facing = DELTA_TO_DIR.get((fdx, fdy))
                if facing is None:
                    continue
                # Check feed: any adjacent harvester or connected transport
                # on a non-facing side
                has_feed = False
                for adx, ady in DIR4_DELTA:
                    if (adx, ady) == (fdx, fdy):
                        continue
                    fax, fay = gx + adx, gy + ady
                    if not s.in_bounds(fax, fay):
                        continue
                    fai = fay * w + fax
                    fbld = s.building[fai]
                    if fbld is None or fbld.team != s.my_team:
                        continue
                    if isinstance(fbld, BuildingHarvester):
                        has_feed = True  # harvesters output all cardinal
                        break
                    if fai in s.connected_transport and _tile_has_correct_transport(
                        s, fai, gi, w
                    ):
                        has_feed = True  # transport outputs toward us
                        break
                if not has_feed:
                    _log(f"    ({gx},{gy}) no_feed face=({fdx},{fdy})", ct.get_id())
                    continue
                d = abs(pos.x - gx) + abs(pos.y - gy)
                if d < best_gdist:
                    best_gdist = d
                    best_gpos = Position(gx, gy)
                    best_facing = facing
        if best_gpos is not None:
            break  # found on this ring, don't search farther

    if best_gpos is None:
        _log(f"  reactive_gunner: no valid placement near ({ttx},{tty})", ct.get_id())
        return None

    gi = best_gpos.y * w + best_gpos.x
    if pos.distance_squared(best_gpos) > 2:
        builder.nav.set_goal(best_gpos)
        moved = builder.nav.step(ct)
        return f"def:gunner_walk({best_gpos.x},{best_gpos.y})", moved
    _clear_tile(ct, s, gi, best_gpos)
    if best_facing is not None and ct.can_build_gunner(best_gpos, best_facing):
        ct.build_gunner(best_gpos, best_facing)
        _log(
            f"    PLACED gunner({best_gpos.x},{best_gpos.y}) facing={best_facing.name}",
            ct.get_id(),
        )
        return f"def:gunner({best_gpos.x},{best_gpos.y})", True

    return None


def _task_repair_chain(builder: Builder, ct: Controller) -> tuple[str, bool] | None:
    s = builder.state
    disconnected = s.my_harvesters - s.connected_harvesters
    if not disconnected:
        return None
    # Use existing connect logic
    return _task_connect(builder, ct, disconnected)


def _task_heal_infra(builder: Builder, ct: Controller) -> tuple[str, bool] | None:
    s = builder.state
    w = s.w
    pos = ct.get_position()

    # Skip healing buildings that have an enemy bot actively attacking them.
    # Healing is a losing trade (we spend 1 Ti/turn, enemy does 2 dmg/2 Ti
    # but keeps attacking forever). Let intercept gunner eliminate the threat.
    tiles_under_attack: set[int] = set()
    for uid in ct.get_nearby_units():
        if ct.get_team(uid) == s.my_team:
            continue
        if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
            continue
        epos = ct.get_position(uid)
        ei = epos.y * w + epos.x
        bld = s.building[ei]
        if bld is None or bld.team != s.my_team:
            continue
        if isinstance(bld, (BuildingMarker, BuildingRoad)):
            continue
        bid = ct.get_tile_building_id(epos)
        if bid is None:
            continue
        if ct.get_hp(bid) < ct.get_max_hp(bid):
            tiles_under_attack.add(ei)

    if ct.get_action_cooldown() != 0:
        return None

    ti_res, _ = ct.get_global_resources()
    if ti_res < 1:
        return None

    # Find lowest HP% friendly building in vision
    # Skip buildings where another friendly bot is already adjacent
    friendly_positions: list[Position] = []
    my_id = ct.get_id()
    for uid in ct.get_nearby_units():
        if uid == my_id:
            continue
        if ct.get_team(uid) == s.my_team:
            friendly_positions.append(ct.get_position(uid))

    best_pos: Position | None = None
    best_ratio = 1.0
    for bid in ct.get_nearby_buildings():
        if ct.get_team(bid) != s.my_team:
            continue
        etype = ct.get_entity_type(bid)
        if etype == EntityType.MARKER:
            continue
        if etype == EntityType.ROAD:
            # Only heal roads adjacent to our harvesters
            rpos = ct.get_position(bid)
            rpos.y * w + rpos.x
            adj_harv = False
            for ddx, ddy in DIR4_DELTA:
                ax, ay = rpos.x + ddx, rpos.y + ddy
                if s.in_bounds(ax, ay):
                    abld = s.building[ay * w + ax]
                    if isinstance(abld, BuildingHarvester) and abld.team == s.my_team:
                        adj_harv = True
                        break
            if not adj_harv:
                continue
        hp = ct.get_hp(bid)
        max_hp = ct.get_max_hp(bid)
        if hp >= max_hp:
            continue
        bpos = ct.get_position(bid)
        bi = bpos.y * w + bpos.x
        # Skip buildings under active enemy attack — healing is futile,
        # let the intercept gunner handle it
        if bi in tiles_under_attack:
            continue
        if any(fp.distance_squared(bpos) <= 2 for fp in friendly_positions):
            continue
        ratio = hp / max_hp
        if ratio < best_ratio:
            best_ratio = ratio
            best_pos = bpos

    if best_pos is None or best_ratio >= 1.0:
        return None

    # Only heal when missing HP >= 4 (heal restores 4 HP, don't waste Ti)
    # But still walk to buildings being attacked
    if pos.distance_squared(best_pos) <= 2:
        bid_h = ct.get_tile_building_id(best_pos)
        if bid_h is not None:
            missing = ct.get_max_hp(bid_h) - ct.get_hp(bid_h)
            if missing >= 4 and ct.can_heal(best_pos):
                ct.heal(best_pos)
                return f"heal_infra:heal({best_pos.x},{best_pos.y})", True
        # Only guard (block other tasks) if enemy bot is actively attacking
        if best_pos in s.unit_tiles:
            return f"heal_infra:guard({best_pos.x},{best_pos.y})", False
        # Not under active attack, missing < 4 -- let other tasks run
        return None
    builder.nav.set_goal(best_pos)
    moved = builder.nav.step(ct)
    return f"heal_infra:walk({best_pos.x},{best_pos.y})", moved


def _task_barrier_harvesters(
    builder: Builder, ct: Controller
) -> tuple[str, bool] | None:
    s = builder.state
    w = s.w
    pos = ct.get_position()

    b_cost, _ = ct.get_barrier_cost()
    ti_res, _ = ct.get_global_resources()
    if ti_res < b_cost:
        return None

    for hi in s.connected_harvesters:
        hx, hy = hi % w, hi // w
        for dx, dy in DIR4_DELTA:
            nx, ny = hx + dx, hy + dy
            if not s.in_bounds(nx, ny):
                continue
            ni = ny * w + nx
            if ni in s.connected_transport:
                continue  # don't barrier our own transport chain
            env = s.env[ni]
            if env is not None and env in (
                Environment.WALL,
                Environment.ORE_TITANIUM,
                Environment.ORE_AXIONITE,
            ):
                continue
            bld = s.building[ni]
            barrier_pos = Position(nx, ny)
            # Enemy building adjacent to harvester? Walk onto it and fire.
            if (
                bld is not None
                and bld.team != s.my_team
                and not isinstance(bld, BuildingMarker)
            ):
                if pos == barrier_pos:
                    fbid = ct.get_tile_building_id(pos)
                    if (
                        fbid is not None
                        and ct.get_team(fbid) != s.my_team
                        and ct.can_fire(pos)
                    ):
                        ct.fire(pos)
                        return f"barrier:fire({nx},{ny})", True
                if builder.nav.is_passable(barrier_pos):
                    builder.nav.set_goal(barrier_pos)
                    moved = builder.nav.step(ct)
                    return f"barrier:walk_fire({nx},{ny})", moved
                continue
            # Skip tiles that already have our important buildings
            if bld is not None and not isinstance(bld, (BuildingRoad, BuildingMarker)):
                continue
            if barrier_pos in s.unit_tiles:
                continue
            if pos.distance_squared(barrier_pos) <= 2 and barrier_pos != pos:
                _destroy_friendly(ct, barrier_pos, allow_barrier=True)
                if ct.can_build_barrier(barrier_pos):
                    ct.build_barrier(barrier_pos)
                    return f"barrier:place({nx},{ny})", True
            else:
                # Walk to an adjacent walkable tile of the barrier spot
                best_adj: Position | None = None
                best_d = 1_000_000
                for adx, ady in DIR4_DELTA:
                    ax, ay = nx + adx, ny + ady
                    if not s.in_bounds(ax, ay):
                        continue
                    adj = Position(ax, ay)
                    if not builder.nav.is_passable(adj):
                        continue
                    d = (pos.x - ax) ** 2 + (pos.y - ay) ** 2
                    if d < best_d:
                        best_d = d
                        best_adj = adj
                if best_adj is not None:
                    builder.nav.set_goal(best_adj)
                    moved = builder.nav.step(ct)
                    return f"barrier:walk({nx},{ny})", moved

    return None


def _task_patrol(builder: Builder, ct: Controller) -> tuple[str, bool]:
    """Walk to least-recently-seen walkable infra tile. Sticky until seen."""
    s = builder.state
    w = s.w
    pos = ct.get_position()
    now = s.age + s.birthday

    infra = s.connected_transport | s.core_tiles
    if not infra:
        return _task_explore(builder, ct)

    # Sticky target -- only repick when we've SEEN the target tile
    pt = getattr(builder, "_patrol_target", None)
    if pt is not None:
        ptx, pty = pt % w, pt // w
        arrived = (pos.x - ptx) ** 2 + (pos.y - pty) ** 2 <= 2
        if pt not in infra or arrived:
            pt = None

    if pt is None:
        best_ti = -1
        best_seen = now + 1
        pos_i = pos.y * w + pos.x
        for ti in infra:
            if ti == pos_i:
                continue
            if s.last_seen[ti] >= now:
                continue  # already visible
            if s.last_seen[ti] < best_seen:
                best_seen = s.last_seen[ti]
                best_ti = ti
        pt = best_ti if best_ti != -1 else None
        builder._patrol_target = pt

    if pt is None:
        return _task_explore(builder, ct)

    tx, ty = pt % w, pt // w
    builder.nav.set_goal(Position(tx, ty))
    moved = builder.nav.step(ct)
    return f"patrol:walk({tx},{ty})", moved
