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
    """Place a gunner adjacent to our transport chain to kill enemy raiders.

    Triggers when an enemy builder bot is attacking our infrastructure
    (standing on a tile where our building has HP < max). We find an empty
    or clearable tile adjacent to connected transport with flow, with LoS
    to the raider tile. The transport feeds the gunner from a non-facing side.
    The gunner kills the raider (10 dmg/shot vs 40 HP = 4 shots), then
    self-destructs after 15 idle rounds.
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

    # Find enemy builder bots actively attacking our buildings
    raider_tiles: list[tuple[int, Position]] = []  # (building_tile_idx, bot_pos)
    for uid in ct.get_nearby_units():
        if ct.get_team(uid) == my_team:
            continue
        if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
            continue
        epos = ct.get_position(uid)
        ei = epos.y * w + epos.x
        # Enemy bot must be standing on our building that's damaged
        bld = s.building[ei]
        if bld is None or bld.team != my_team:
            continue
        if isinstance(bld, (BuildingMarker, BuildingRoad)):
            continue  # don't care about roads/markers
        bid = ct.get_tile_building_id(epos)
        if bid is None:
            continue
        if ct.get_hp(bid) >= ct.get_max_hp(bid):
            continue  # not damaged — bot is just passing through
        raider_tiles.append((ei, epos))

    if not raider_tiles:
        return None

    # Don't place if we already have a friendly gunner covering any raider
    for _, epos in raider_tiles:
        eti = epos.y * w + epos.x
        if _has_friendly_gunner_covering(s, eti):
            return None  # already handled

    # For each raider, find an empty/clearable tile ADJACENT to connected
    # transport with flow. The gunner faces the raider; the transport feeds
    # from a non-facing side.
    best_gpos: Position | None = None
    best_facing: Direction | None = None
    best_gdist = 1_000_000

    for _, epos in raider_tiles:
        ex, ey = epos.x, epos.y
        # Search connected transport tiles with flow
        for ti in s.connected_transport:
            if ti not in s.tiles_with_flow and ti not in s.flow_seen:
                continue
            ftx, fty = ti % w, ti // w
            # Check cardinal neighbors of this transport for gunner placement
            for adx, ady in DIR4_DELTA:
                gx, gy = ftx + adx, fty + ady
                if not s.in_bounds(gx, gy):
                    continue
                gi = gy * w + gx
                # Must be within gunner range of raider (r²≤13)
                if (gx - ex) ** 2 + (gy - ey) ** 2 > 13:
                    continue
                # Tile must be buildable (empty, or own road/marker/barrier)
                if not _can_place_gunner_at(s, gi):
                    continue
                # Compute facing toward raider
                fdx = 0 if ex == gx else (1 if ex > gx else -1)
                fdy = 0 if ey == gy else (1 if ey > gy else -1)
                if fdx == 0 and fdy == 0:
                    continue
                # Transport must feed from non-facing side
                feed_dx, feed_dy = ftx - gx, fty - gy
                if (feed_dx, feed_dy) == (fdx, fdy):
                    continue  # transport is on the facing side — can't receive
                # Verify transport actually outputs toward the gunner tile
                if not _tile_has_correct_transport(s, ti, gi, w):
                    # Also accept harvesters (output all cardinal)
                    tbld = s.building[ti]
                    if not isinstance(tbld, BuildingHarvester):
                        continue
                # Verify LoS to raider
                if not _ray_clear_to(s, gx, gy, fdx, fdy, ex, ey):
                    continue
                facing = DELTA_TO_DIR.get((fdx, fdy))
                if facing is None:
                    continue
                d = abs(pos.x - gx) + abs(pos.y - gy)
                if d < best_gdist:
                    best_gdist = d
                    best_gpos = Position(gx, gy)
                    best_facing = facing

    if best_gpos is None or best_facing is None:
        return None

    gi = best_gpos.y * w + best_gpos.x

    _log(
        f"  intercept_raider: gunner at ({best_gpos.x},{best_gpos.y}) "
        f"facing={best_facing.name}",
        ct.get_id(),
    )

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
        _log(
            f"  PLACED intercept gunner({best_gpos.x},{best_gpos.y}) "
            f"facing={best_facing.name}",
            ct.get_id(),
        )
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
