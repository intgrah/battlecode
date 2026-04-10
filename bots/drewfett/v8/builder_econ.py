"""Econ role tasks: connect, harvest, explore."""

from __future__ import annotations

from typing import TYPE_CHECKING

from builder_helpers import (
    _BRANCH_CAPACITY,
    _destroy_friendly,
    _has_nearby_threat,
    _log,
    _tile_has_correct_transport,
)
from building import (
    BuildingBarrier,
    BuildingMarker,
    BuildingRoad,
)
from cambc import Controller, Direction, Environment, Position
from chain_astar import ChainAstar
from util import DELTA_TO_DIR, DIR4_DELTA

if TYPE_CHECKING:
    from builder import Builder
    from nav import NavBfs
    from state import State


def _run_econ(builder: Builder, ct: Controller) -> tuple[str, bool]:
    s = builder.state

    # Reactive gunner — econ builders also counter enemy turrets threatening our infra
    from builder_defense import _task_reactive_gunner

    result = _task_reactive_gunner(builder, ct)
    if result is not None:
        return result

    # Barrier exposed ore if enemy bots nearby
    result = _task_barrier_ore(builder, ct)
    if result is not None:
        return result

    # Connect unconnected harvesters
    unconnected = s.my_harvesters - s.connected_harvesters
    if unconnected:
        result = _task_connect(builder, ct, unconnected)
        if result is not None:
            return result

    # Place new harvesters
    result = _task_harvest(builder, ct)
    if result is not None:
        return result

    # Explore map
    return _task_explore(builder, ct)


def _task_barrier_ore(builder: Builder, ct: Controller) -> tuple[str, bool] | None:
    """Barrier unprotected ore tiles if enemy bots are nearby."""
    s = builder.state
    w = s.w
    pos = ct.get_position()

    # Find nearby enemy bots
    enemy_bots: list[Position] = []
    for uid in ct.get_nearby_units():
        if ct.get_team(uid) != s.my_team:
            enemy_bots.append(ct.get_position(uid))
    if not enemy_bots:
        return None

    # Check ore tiles we know about that aren't already harvested or barriered
    for oi in builder.ti_ore.positions:
        if oi in s.my_harvesters or oi in s.en_harvesters:
            continue
        ox, oy = oi % w, oi // w
        ore_pos = Position(ox, oy)

        # Already has a building (barrier, our stuff, enemy stuff) → skip
        bld = s.building[oi]
        if bld is not None:
            continue

        # Enemy bot within Manhattan 3 of this ore?
        threat = any(abs(ox - ep.x) + abs(oy - ep.y) <= 3 for ep in enemy_bots)
        if not threat:
            continue

        # Barrier it if adjacent
        if pos.distance_squared(ore_pos) <= 2 and ore_pos != pos:
            b_cost, _ = ct.get_barrier_cost()
            ti_res, _ = ct.get_global_resources()
            if ti_res >= b_cost and ct.can_build_barrier(ore_pos):
                ct.build_barrier(ore_pos)
                return f"barrier_ore({ox},{oy})", True

        # Walk toward it if close
        if pos.distance_squared(ore_pos) <= 18:  # ~Manhattan 4
            builder.nav.set_goal(ore_pos)
            moved = builder.nav.step(ct)
            return f"barrier_ore:walk({ox},{oy})", moved

    return None


def _task_connect(
    builder: Builder, ct: Controller, unconnected: set[int]
) -> tuple[str, bool] | None:
    """Connect nearest unconnected harvester. Caches path for stability."""
    s = builder.state
    w = s.w
    pos = ct.get_position()

    # Only connect harvesters THIS builder placed
    my_unconnected = unconnected & builder._my_harvesters

    # Stick with current target if still unconnected
    if (
        builder._connect_harvester is not None
        and builder._connect_harvester in my_unconnected
    ):
        best_hi = builder._connect_harvester
    else:
        best_hi = None
        best_dist = 1_000_000
        for hi in my_unconnected:
            hx, hy = hi % w, hi // w
            d = (pos.x - hx) ** 2 + (pos.y - hy) ** 2
            if d < best_dist:
                best_dist = d
                best_hi = hi

    if best_hi is None:
        builder._connect_harvester = None
        builder._connect_path = None
        return None

    builder._connect_harvester = best_hi
    hx, hy = best_hi % w, best_hi // w

    # Validate cached path: endpoint valid + no enemy buildings appeared on path
    path = builder._connect_path
    if path is not None:
        end_ti = path[-1]
        end_bn = s.bottleneck.get(end_ti, 0)
        still_valid = (
            end_bn < _BRANCH_CAPACITY
            and (end_ti in s.connected_transport or end_ti in s.core_tiles)
            and path[0] == best_hi  # same harvester
        )
        if still_valid:
            # Check no enemy buildings appeared on the path
            for pi in path:
                pbld = s.building[pi]
                if (
                    pbld is not None
                    and pbld.team != s.my_team
                    and not isinstance(pbld, BuildingMarker)
                ):
                    still_valid = False
                    break
        if not still_valid:
            path = None
            builder._connect_path = None

    # Recompute A* if no cached path
    if path is None:
        goals = _capacity_filtered_goals(s)
        if not goals:
            # Everything is full or stale — can't connect safely
            return f"connect:no_valid_goals h=({hx},{hy})", False

        search = ChainAstar(
            s,
            hx,
            hy,
            goals,
            bottleneck=s.bottleneck,
            capacity=_BRANCH_CAPACITY,
        )
        path = search.compute(within_budget=lambda: ct.get_cpu_time_elapsed() < 1500)

        if path is None:
            builder._connect_path = None
            return f"connect:no_path h=({hx},{hy})", False

        builder._connect_path = path

    end_ti = path[-1]
    end_bn = s.bottleneck.get(end_ti, 0)

    # Find first gap in the path (from harvester toward core).
    # Sequential building ensures we complete chains without bouncing.
    gap_idx: int | None = None
    for k in range(len(path) - 1):
        ci = path[k]
        ni = path[k + 1]
        if _tile_has_correct_transport(s, ci, ni, w):
            continue
        gap_idx = k
        break

    if gap_idx is None:
        # Path is complete -- harvester is now connected
        return f"connect:complete h=({hx},{hy})", False

    ci = path[gap_idx]
    ni = path[gap_idx + 1]
    cx, cy = ci % w, ci // w
    nx, ny = ni % w, ni // w
    build_pos = Position(cx, cy)
    tag = f"connect:h=({hx},{hy}) gap=({cx},{cy})"

    # Check if adjacent to gap -- if so, build + walk toward next gap
    if pos.distance_squared(build_pos) <= 2:
        return _build_at_gap(builder, ct, cx, cy, nx, ny, build_pos, tag, path, gap_idx)

    # Walk toward gap (may build roads to get there)
    builder.nav.set_goal(build_pos)
    moved = builder.nav.step(ct)
    return f"{tag} walk->({cx},{cy})", moved


def _walk_toward_next_gap(
    builder: Builder, ct: Controller, path: list[int], from_k: int
) -> None:
    """After building, use remaining movement to walk toward next gap."""
    s = builder.state
    w = s.w
    for k in range(from_k, len(path) - 1):
        ci = path[k]
        ni = path[k + 1]
        if _tile_has_correct_transport(s, ci, ni, w):
            continue
        # Found next gap — try to walk toward it
        gx, gy = ci % w, ci // w
        target = Position(gx, gy)
        direction = ct.get_position().direction_to(target)
        if direction != Direction.CENTRE and ct.can_move(direction):
            ct.move(direction)
        return


def _build_at_gap(
    builder: Builder,
    ct: Controller,
    cx: int,
    cy: int,
    nx: int,
    ny: int,
    build_pos: Position,
    tag: str,
    path: list[int] | None = None,
    gap_idx: int = 0,
    destroy_barriers: bool = False,
) -> tuple[str, bool]:
    """Build conveyor or bridge at the gap tile."""
    s = builder.state
    w = s.w
    ci = cy * w + cx
    ni = ny * w + nx

    # Debug: log what's on the tiles
    ci_bld = s.building[ci]
    ni_bld = s.building[ni]
    ci_name = type(ci_bld).__name__[8:] if ci_bld else "empty"
    ni_name = type(ni_bld).__name__[8:] if ni_bld else "empty"
    ci_team = "own" if ci_bld and ci_bld.team == s.my_team else "en" if ci_bld else ""
    ni_team = "own" if ni_bld and ni_bld.team == s.my_team else "en" if ni_bld else ""
    ci_conn = "conn" if ci in s.connected_transport else ""
    _log(
        f"  gap@({cx},{cy})={ci_team}{ci_name}{ci_conn} -> ({nx},{ny})={ni_team}{ni_name} mode={'atk' if destroy_barriers else 'eco'}",
        0,
    )

    # Pre-check (econ only): can we remove existing building on gap tile?
    if not destroy_barriers:
        gap_bld = s.building[ci]
        if gap_bld is not None and not (
            isinstance(gap_bld, BuildingMarker)
            or (
                gap_bld.team == s.my_team
                and isinstance(gap_bld, (BuildingRoad, BuildingBarrier))
            )
        ):
            builder._connect_path = None
            return f"{tag} tile_blocked:recompute", False

    dx, dy = nx - cx, ny - cy
    conv_dir = DELTA_TO_DIR.get((dx, dy))

    if conv_dir is None:
        # Bridge hop — verify target tile is usable
        target_env = s.env[ni]
        if target_env == Environment.WALL:
            if not destroy_barriers:
                builder._connect_path = None
            return f"{tag} bridge_target_blocked({nx},{ny}):recompute", False
        # Check for enemy building or danger zone on target
        target_bld = s.building[ni]
        if (
            target_bld is not None
            and target_bld.team != s.my_team
            and not isinstance(target_bld, BuildingMarker)
        ):
            if not destroy_barriers:
                builder._connect_path = None
            return f"{tag} bridge_target_enemy({nx},{ny}):recompute", False
        if ni in s.danger_zones:
            if not destroy_barriers:
                builder._connect_path = None
            return f"{tag} bridge_target_danger({nx},{ny}):recompute", False
        target_pos = Position(nx, ny)
        b_cost, _ = ct.get_bridge_cost()
        ti_res, _ = ct.get_global_resources()
        if ti_res < b_cost:
            return f"{tag} wait_ti(bridge)", False
        if ci not in s.connected_transport:
            _destroy_friendly(ct, build_pos, allow_barrier=True)
        if ct.can_build_bridge(build_pos, target_pos):
            ct.build_bridge(build_pos, target_pos)
            from building import BuildingBridge as BldBridge

            s.building[ci] = BldBridge(s.my_team, target_pos)
            s.my_transport.add(ci)
            _walk_toward_next_gap(builder, ct, path, gap_idx + 1)
            return f"{tag} bridge({cx},{cy})->({nx},{ny})", True
        # Build failed — try to destroy any own building blocking us
        if destroy_barriers:
            bid = ct.get_tile_building_id(build_pos)
            if bid is not None and ct.get_team(bid) == ct.get_team():
                if ct.can_destroy(build_pos):
                    ct.destroy(build_pos)
                    s.building[ci] = None
                    s.my_transport.discard(ci)
                    return f"{tag} cleared({cx},{cy})", False
        else:
            builder._connect_path = None
        return f"{tag} bridge_cant_build:recompute", False

    # Cardinal conveyor — verify tiles
    next_env = s.env[ni]
    if next_env == Environment.WALL:
        if destroy_barriers:
            pass  # frontier model — caller handles replan
        else:
            builder._connect_path = None
        return f"{tag} conv_target_wall({nx},{ny}):recompute", False
    # Enemy building at next tile — recompute path to route around it
    # In attack mode (destroy_barriers), allow enemy roads (fire at them later)
    next_bld = s.building[ni]
    if (
        next_bld is not None
        and next_bld.team != s.my_team
        and not isinstance(next_bld, BuildingMarker)
    ):
        if destroy_barriers and isinstance(next_bld, BuildingRoad):
            pass  # attack: build conveyor pointing at enemy road, fire later
        else:
            if not destroy_barriers:
                builder._connect_path = None
            return f"{tag} conv_target_enemy({nx},{ny}):recompute", False
    cur_env = s.env[ci]
    if cur_env == Environment.WALL:
        if destroy_barriers:
            pass  # frontier model — caller handles replan
        else:
            builder._connect_path = None
        return f"{tag} conv_tile_blocked({cx},{cy}):recompute", False
    c_cost, _ = ct.get_conveyor_cost()
    ti_res, _ = ct.get_global_resources()
    if ti_res < c_cost:
        return f"{tag} wait_ti(conv)", False
    _destroy_friendly(ct, build_pos, allow_barrier=True)
    if ct.can_build_conveyor(build_pos, conv_dir):
        ct.build_conveyor(build_pos, conv_dir)
        from building import BuildingConveyor as BldConveyor

        s.building[ci] = BldConveyor(s.my_team, conv_dir)
        s.my_transport.add(ci)
        _walk_toward_next_gap(builder, ct, path, gap_idx + 1)
        return f"{tag} conv({cx},{cy})->{conv_dir.name}", True
    # Build failed — try to destroy any own building blocking us
    if destroy_barriers:
        bid = ct.get_tile_building_id(build_pos)
        if bid is not None and ct.get_team(bid) == ct.get_team():
            if ct.can_destroy(build_pos):
                ct.destroy(build_pos)
                s.building[ci] = None
                s.my_transport.discard(ci)
                return f"{tag} cleared({cx},{cy})", False  # retry next turn
    if not destroy_barriers:
        builder._connect_path = None
    return f"{tag} conv_cant_build:recompute", False


def _capacity_filtered_goals(s: State) -> set[int]:
    """Goals = core tiles + connected transport with spare capacity."""
    goals: set[int] = set(s.core_tiles)
    for ti in s.connected_transport:
        if s.bottleneck.get(ti, 0) < _BRANCH_CAPACITY:
            goals.add(ti)
    return goals


def _task_harvest(
    builder: Builder, ct: Controller, *, target_pos: Position | None = None
) -> tuple[str, bool] | None:
    s = builder.state
    w = s.w
    pos = ct.get_position()

    unharvested = builder.ti_ore.positions - s.my_harvesters - s.en_harvesters
    # Remove temporarily blocked ore (but NOT ore_with_bot here —
    # that would break sticky targets causing harvest/explore flicker)
    blocked = getattr(builder, "_blocked_ore", {})
    now = s.age + s.birthday
    unharvested = {oi for oi in unharvested if blocked.get(oi, 0) <= now}
    if not unharvested:
        builder._harvest_target = None
        return None

    # Phase 1: adjacent to ore -- secure area then place harvester
    enemy_bot_positions: list[Position] = []
    for uid in ct.get_nearby_units():
        if ct.get_team(uid) != s.my_team:
            enemy_bot_positions.append(ct.get_position(uid))

    for dx, dy in DIR4_DELTA:
        ni = (pos.y + dy) * w + (pos.x + dx)
        if ni not in unharvested:
            continue
        ore_pos = Position(pos.x + dx, pos.y + dy)
        if ore_pos in s.unit_tiles:
            continue

        # Enemy bots nearby → don't harvest yet (barrier_ore task handles protection)
        enemy_nearby = any(
            abs(ore_pos.x - ep.x) + abs(ore_pos.y - ep.y) <= 3
            for ep in enemy_bot_positions
        )
        if enemy_nearby:
            continue

        # Check ore tile itself — skip if non-removable enemy building
        existing = s.building[ni]
        if existing is not None:
            if isinstance(existing, (BuildingRoad, BuildingMarker)):
                pass  # removable
            elif (
                isinstance(existing, BuildingBarrier)
                and existing.team == s.my_team
                and not _has_nearby_threat(s, ni)
            ):
                pass  # our barrier, no threat — safe to remove
            else:
                continue

        # ── Control all 4 adjacent tiles BEFORE placing harvester ──
        # First pass: check for blockers (enemy non-road buildings → skip ore)
        has_blocker = False
        enemy_roads: list[tuple[int, int]] = []
        empty_tiles: list[tuple[int, int]] = []
        for adx, ady in DIR4_DELTA:
            ax, ay = ore_pos.x + adx, ore_pos.y + ady
            if not s.in_bounds(ax, ay):
                continue
            ai = ay * w + ax
            if s.env[ai] == Environment.WALL:
                continue
            abld = s.building[ai]
            if abld is not None and abld.team != s.my_team:
                if isinstance(abld, (BuildingRoad, BuildingMarker)):
                    if isinstance(abld, BuildingRoad):
                        enemy_roads.append((ax, ay))
                else:
                    has_blocker = True
                    break
            elif abld is None:
                empty_tiles.append((ax, ay))
            # else: our building → controlled
        if has_blocker:
            continue

        # Second pass: control uncontrolled tiles (fire roads, place our roads)
        if enemy_roads:
            # Fire at closest reachable enemy road
            for rx, ry in sorted(
                enemy_roads, key=lambda p: pos.distance_squared(Position(p[0], p[1]))
            ):
                rpos = Position(rx, ry)
                if pos == rpos and ct.can_fire(rpos):
                    ct.fire(rpos)
                    return f"harvest:fire_road({rx},{ry})", True
                builder.nav.set_goal(rpos)
                moved = builder.nav.step(ct)
                return f"harvest:walk_road({rx},{ry})", moved

        if empty_tiles:
            # Place road on closest empty tile
            for ex, ey in sorted(
                empty_tiles, key=lambda p: pos.distance_squared(Position(p[0], p[1]))
            ):
                epos = Position(ex, ey)
                if pos.distance_squared(epos) <= 2 and ct.can_build_road(epos):
                    ct.build_road(epos)
                    return f"harvest:road({ex},{ey})", True
                builder.nav.set_goal(epos)
                moved = builder.nav.step(ct)
                return f"harvest:walk_prep({ex},{ey})", moved

        # All sides controlled — place harvester
        h_cost, _ = ct.get_harvester_cost()
        ti, _ = ct.get_global_resources()
        if ti < h_cost:
            return "harvest:wait_ti", False
        _destroy_friendly(ct, ore_pos, allow_barrier=True)
        if ct.can_build_harvester(ore_pos):
            ct.build_harvester(ore_pos)
            builder._harvest_target = None
            builder._my_harvesters.add(ni)
            return f"harvest:place({ore_pos.x},{ore_pos.y})", True
        # Failed — block this ore temporarily so we pick a different one
        builder._harvest_target = None
        builder._blocked_ore = getattr(builder, "_blocked_ore", {})
        builder._blocked_ore[ni] = s.age + s.birthday + 50  # block for 50 turns
        return f"harvest:cant_place({ore_pos.x},{ore_pos.y})", False

    # Phase 2: walk toward committed ore target (sticky -- no oscillation)
    # Re-pick only if current target is gone (harvested, out of unharvested set)
    ht = builder._harvest_target
    if ht is not None and ht not in unharvested:
        ht = None
        builder._harvest_target = None

    if ht is None:
        # Pick best ore: attack → near target, econ → near core/network
        if target_pos is not None:
            # Attack: prefer ore near the enemy target — heavily weight
            # closeness to target, and reject ore too far from it
            tpx, tpy = target_pos.x, target_pos.y
            max_target_dist = (s.w + s.h) // 3  # reject ore beyond this

            def _score(oi: int) -> int:
                ox, oy = oi % w, oi // w
                target_dist = abs(ox - tpx) + abs(oy - tpy)
                if target_dist > max_target_dist:
                    return 1_000_000  # too far from target
                walk_dist = max(abs(pos.x - ox), abs(pos.y - oy))
                return walk_dist + target_dist * 3

        else:
            # Econ: prefer ore near connected network
            network = s.connected_transport | s.core_tiles
            core_x, core_y = s.core_pos.x, s.core_pos.y

            def _score(oi: int) -> int:
                ox, oy = oi % w, oi // w
                walk_dist = max(abs(pos.x - ox), abs(pos.y - oy))
                if network:
                    conn_dist = min(
                        abs(ox - ti % w) + abs(oy - ti // w) for ti in network
                    )
                else:
                    conn_dist = abs(ox - core_x) + abs(oy - core_y)
                return walk_dist + conn_dist * 2

        # Skip ore with enemy buildings, bots, or unreachable
        valid_ore = set()
        ore_with_bot = {p.y * w + p.x for p in s.unit_tiles}
        reach = s.reachable
        for oi in unharvested:
            bld = s.building[oi]
            if (
                bld is not None
                and bld.team != s.my_team
                and not isinstance(bld, BuildingMarker)
            ):
                continue
            if oi in ore_with_bot:
                continue
            if reach is not None and not reach.is_reachable_idx(oi):
                continue
            valid_ore.add(oi)
        scored = sorted(
            [(sc, oi) for oi in valid_ore if (sc := _score(oi)) < 1_000_000]
        )
        if scored:
            ht = scored[0][1]
            builder._harvest_target = ht

    if ht is None:
        return None

    ore_pos = Position(ht % w, ht // w)
    # Walk to cardinal neighbor of ore closest to core (must be passable)
    best_adj: Position | None = None
    best_d = 1_000_000
    core_x, core_y = s.core_pos.x, s.core_pos.y
    for dx, dy in DIR4_DELTA:
        ax, ay = ore_pos.x + dx, ore_pos.y + dy
        if not s.in_bounds(ax, ay):
            continue
        ai = ay * w + ax
        env = s.env[ai]
        if env is not None and env == Environment.WALL:
            continue
        d = abs(core_x - ax) + abs(core_y - ay)
        if d < best_d:
            best_d = d
            best_adj = Position(ax, ay)

    if best_adj is not None:
        # Already adjacent but can't place? Block this ore and move on.
        if pos.distance_squared(ore_pos) <= 2:
            builder._harvest_target = None
            builder._blocked_ore = getattr(builder, "_blocked_ore", {})
            builder._blocked_ore[ht] = s.age + s.birthday + 30
            return None
        builder.nav.set_goal(best_adj)
        moved = builder.nav.step(ct)
        # Detect stuck OR oscillation (moving but not progressing)
        _prev = getattr(builder, "_harvest_anchor", None)
        if _prev is not None and pos.distance_squared(_prev) <= 4:
            builder._harvest_stuck = getattr(builder, "_harvest_stuck", 0) + 1
        else:
            builder._harvest_stuck = 0
            builder._harvest_anchor = pos
        if builder._harvest_stuck >= 6:
            builder._harvest_target = None
            builder._harvest_stuck = 0
            builder._blocked_ore = getattr(builder, "_blocked_ore", {})
            builder._blocked_ore[ht] = s.age + s.birthday + 50
            return None
        return f"harvest:walk->ore({ore_pos.x},{ore_pos.y})", moved

    return None


def _task_explore(builder: Builder, ct: Controller) -> tuple[str, bool]:
    target = builder.explore.target
    if target is None:
        return "explore:no_target", False

    # Econ builders: don't wander too far from core
    s = builder.state
    pos = ct.get_position()
    core_dist = abs(pos.x - s.core_pos.x) + abs(pos.y - s.core_pos.y)
    if core_dist > 20:
        # Too far — walk back toward core
        builder.nav.set_goal(s.core_pos)
        moved = builder.nav.step(ct)
        return "explore:return_core", moved

    builder.nav.set_goal(target)
    moved = builder.nav.step(ct)
    return f"explore:walk->({target.x},{target.y})", moved


def _task_explore_enemy(builder: Builder, ct: Controller) -> tuple[str, bool]:
    """Explore unseen tiles on the enemy half, biased toward enemy core.

    Sticky target — pick once, walk until seen, then repick.
    """
    s = builder.state
    w, h = s.w, s.h
    pos = ct.get_position()
    rnd = ct.get_current_round()

    # Enemy core estimate
    if s.en_core_pos is not None:
        ex, ey = s.en_core_pos.x, s.en_core_pos.y
    else:
        ex, ey = w - 1 - s.core_pos.x, h - 1 - s.core_pos.y

    # Sticky target — only repick if current target is recently seen or None
    et = getattr(builder, "_explore_enemy_target", None)
    if et is not None:
        eti = et.y * w + et.x
        if s.last_seen[eti] >= rnd - 5:
            et = None  # we've seen it recently, pick new

    # Oscillation detection — if stuck near same spot for 8 turns, repick
    _ee_stuck = getattr(builder, "_explore_enemy_stuck", 0)
    _ee_last = getattr(builder, "_explore_enemy_last_pos", None)
    if _ee_last is not None and pos.distance_squared(_ee_last) <= 2:
        _ee_stuck += 1
    else:
        _ee_stuck = 0
    builder._explore_enemy_last_pos = pos
    builder._explore_enemy_stuck = _ee_stuck
    if _ee_stuck >= 8 and et is not None:
        et = None  # force repick
        builder._explore_enemy_stuck = 0

    if et is None:
        best_score = 1_000_000
        cx, cy = s.core_pos.x, s.core_pos.y
        reach = s.reachable
        for y in range(0, h, 3):
            for x in range(0, w, 3):
                i = y * w + x
                # Must be reachable and BFS-passable (not behind barriers)
                if reach is not None and not reach.is_reachable_idx(i):
                    continue
                if s.env[i] == Environment.WALL:
                    continue
                if not builder.nav.is_passable(Position(x, y)):
                    continue
                to_enemy = abs(x - ex) + abs(y - ey)
                staleness = rnd - s.last_seen[i]
                if staleness < 10:
                    continue
                walk_dist = abs(pos.x - x) + abs(pos.y - y)
                # Heavily prefer tiles near enemy core
                score = walk_dist + to_enemy * 2 - staleness
                if score < best_score:
                    best_score = score
                    et = Position(x, y)

    if et is None:
        et = _find_passable_near(builder.nav, s, Position(ex, ey))

    builder._explore_enemy_target = et
    builder.nav.set_goal(et)
    moved = builder.nav.step(ct)
    return f"explore_enemy({et.x},{et.y})", moved


def _find_passable_near(nav: NavBfs, s: State, target: Position) -> Position:
    """Find a passable tile near the target. Returns target if already passable."""
    if nav.is_passable(target):
        return target
    # Search expanding rings for a passable tile
    for r in range(1, 5):
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if abs(dx) != r and abs(dy) != r:
                    continue  # only ring edge
                nx, ny = target.x + dx, target.y + dy
                if s.in_bounds(nx, ny):
                    p = Position(nx, ny)
                    if nav.is_passable(p):
                        return p
    return target  # fallback
