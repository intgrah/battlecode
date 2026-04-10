"""Defense role: reactive gunner, heal, barrier, patrol."""

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
    BuildingHarvester,
    BuildingLauncher,
    BuildingMarker,
    BuildingRoad,
)
from cambc import Controller, EntityType, Environment, Position
from util import DELTA_TO_DIR, DIR4_DELTA

if TYPE_CHECKING:
    from builder import Builder


def _run_defense(builder: Builder, ct: Controller) -> tuple[str, bool]:

    # 1. Reactive gunner against enemy turret in our base
    result = _task_reactive_gunner(builder, ct)
    if result is not None:
        return result

    # 2. Repair broken chains
    result = _task_repair_chain(builder, ct)
    if result is not None:
        return result

    # 3. Heal damaged infra
    result = _task_heal_infra(builder, ct)
    if result is not None:
        return result

    # 4. Barrier harvesters
    result = _task_barrier_harvesters(builder, ct)
    if result is not None:
        return result

    # 5. Patrol (don't waste turns firing at enemy transport — turrets handle that)
    return _task_patrol(builder, ct)


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

    # Also: enemy bots attacking our harvesters or connected transport
    threatened = s.my_harvesters | s.connected_transport
    for uid in ct.get_nearby_units():
        if ct.get_team(uid) == s.my_team:
            continue
        upos = ct.get_position(uid)
        ui = upos.y * w + upos.x
        if ui in threatened and not _has_friendly_gunner_covering(s, ui):
            threats.append(ui)

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

    from builder_helpers import try_place_turret_at

    _log(f"  reactive_gunner: threat=({ttx},{tty})", ct.get_id())

    # Search expanding ring around threat, use unified turret placement
    for r in range(1, 5):
        for gdx in range(-r, r + 1):
            for gdy in range(-r, r + 1):
                if abs(gdx) != r and abs(gdy) != r:
                    continue
                gx, gy = ttx + gdx, tty + gdy
                if not s.in_bounds(gx, gy):
                    continue
                gi = gy * w + gx

                # Find feed source using flow model
                flow = getattr(s, "flow", None)
                feed_ti: int | None = None
                if flow is not None:
                    inputs = flow.inputs_to(gi)
                    if inputs:
                        feed_ti = inputs[0]
                if feed_ti is None:
                    # Check adjacent harvesters as fallback
                    for adx, ady in DIR4_DELTA:
                        fax, fay = gx + adx, gy + ady
                        if s.in_bounds(fax, fay):
                            fai = fay * w + fax
                            if fai in s.my_harvesters or fai in s.en_harvesters:
                                feed_ti = fai
                                break

                result = try_place_turret_at(
                    s, ct, builder.nav, gi, feed_ti, pos, max_walk=8
                )
                if result is not None:
                    return result
        # Don't break early — let the unified function handle distance/passability

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

    # Enemy bot actively attacking our building (HP < max) -> heal if adjacent.
    # Reactive gunner handles offensive response; don't force reroute here.
    for uid in ct.get_nearby_units():
        if ct.get_team(uid) == s.my_team:
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
        if ct.get_hp(bid) >= ct.get_max_hp(bid):
            continue  # not damaged -- bot is just passing through
        # Damaged with enemy on it -- heal opportunistically if adjacent
        if pos.distance_squared(epos) <= 2:
            if ct.get_action_cooldown() == 0 and ct.can_heal(epos):
                ct.heal(epos)
                return f"heal_infra:opp_heal({epos.x},{epos.y})", True

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
        if any(fp.distance_squared(bpos) <= 2 for fp in friendly_positions):
            continue
        ratio = hp / max_hp
        # Boost priority for buildings carrying flow
        bi = bpos.y * w + bpos.x
        flow = getattr(s, "flow", None)
        if flow is not None and bi in flow.connected:
            ratio *= 0.5  # halve ratio = double priority for flow-carrying buildings
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
