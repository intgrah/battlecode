"""Attack role: extend flow toward enemy, place turrets with verified feed.

Uses the FlowModel to:
- Find flow frontier (where our chains can extend)
- Find enemy tappable points (parasitize their flow)
- Verify turret feed before placement
- Track source advancement as chain extends
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from builder_econ import _build_at_gap, _task_explore_enemy, _task_harvest
from builder_helpers import (
    _TRANSPORT_OR_TURRETS,
    DEBUG,
    _log,
    _tile_has_correct_transport,
    try_place_turret_at,
)
from building import (
    BuildingMarker,
    BuildingRoad,
    TRANSPORT,
)
from cambc import Controller, EntityType, Environment, Position
from chain_astar import AttackAstar
from util import DIR4_DELTA

if TYPE_CHECKING:
    from builder import Builder
    from flow import FlowModel
    from nav import NavBfs
    from state import State


class Attack:
    def __init__(self) -> None:
        self.source_ti: int | None = None  # chain frontier
        self._blocked_ore: dict[int, int] = {}


def _run_attack(builder: Builder, ct: Controller) -> tuple[str, bool]:
    a = builder._attack
    s = builder.state
    w = s.w
    pos = ct.get_position()
    flow: FlowModel = s.flow
    rnd = s.age + s.birthday

    # Expire blocked ore
    a._blocked_ore = {k: v for k, v in a._blocked_ore.items() if rnd - v < 50}

    # 1. Validate source (has feed reaching it?)
    if a.source_ti is not None:
        # Source valid if anything feeds it (transport or adjacent harvester)
        if not flow.has_source(a.source_ti) and not _has_adjacent_harvester(s, a.source_ti):
            a.source_ti = None

    # 2. Find source if none
    if a.source_ti is None:
        a.source_ti = _pick_source(flow, s, pos)
    if a.source_ti is None:
        return _fallback(builder, ct, s, pos)

    if DEBUG:
        from vis import Tiles, emit
        emit(atk_source=Tiles(data=[(a.source_ti % w, a.source_ti // w)]))

    # 3. Try turret at source (maybe already near enemy)
    feeder = _feeder_of(flow, s, a.source_ti)
    turret = try_place_turret_at(s, ct, builder.nav, a.source_ti, feeder, pos)
    if turret is not None:
        a.source_ti = None
        return turret

    # 4. Compute chain from source toward enemy
    goals = _goals(s)
    if not goals:
        return _fallback(builder, ct, s, pos)
    goals.discard(a.source_ti)
    if not goals:
        return _fallback(builder, ct, s, pos)

    if ct.get_cpu_time_elapsed() > 1300:
        return _fallback(builder, ct, s, pos)

    chain = AttackAstar(s, a.source_ti, goals).compute(
        within_budget=lambda: ct.get_cpu_time_elapsed() < 1500
    )
    if chain is None or len(chain) < 2:
        a.source_ti = None
        return _fallback(builder, ct, s, pos)

    if DEBUG:
        path_str = "->".join(f"({c % w},{c // w})" for c in chain[:6])
        if len(chain) > 6:
            path_str += f"...({len(chain)})"
        goal_bld = s.building[chain[-1]]
        gname = type(goal_bld).__name__[8:] if goal_bld else "?"
        _log(f"  chain: {path_str} goal=({chain[-1] % w},{chain[-1] // w})={gname}", ct.get_id())
        from vis import Tiles, emit
        emit(atk_chain=Tiles(data=[(c % w, c // w) for c in chain]))

    # 5. Handle first gap
    result = _handle_gap(a, builder, ct, builder.nav, s, flow, chain, pos)
    if result is not None:
        return result

    # 6. Chain complete — try turret at end
    last = chain[-1]
    prev = chain[-2] if len(chain) > 1 else a.source_ti
    turret = try_place_turret_at(s, ct, builder.nav, last, prev, pos)
    if turret is not None:
        a.source_ti = None
        return turret

    return _fallback(builder, ct, s, pos)


# ── Gap handler ────────────────────────────────────────────


def _handle_gap(
    a: Attack,
    builder: Builder,
    ct: Controller,
    nav: NavBfs,
    s: State,
    flow: FlowModel,
    chain: list[int],
    pos: Position,
) -> tuple[str, bool] | None:
    w = s.w

    for k in range(len(chain) - 1):
        ci = chain[k]
        ni = chain[k + 1]

        if _tile_has_correct_transport(s, ci, ni, w):
            continue

        cx, cy = ci % w, ci // w
        ci_bld = s.building[ci]
        build_pos = Position(cx, cy)
        prev_ti = chain[k - 1] if k > 0 else _feeder_of(flow, s, ci)

        if DEBUG:
            ci_name = type(ci_bld).__name__[8:] if ci_bld else "empty"
            ni_bld = s.building[ni]
            ni_name = type(ni_bld).__name__[8:] if ni_bld else "empty"
            _log(f"  gap k={k} ({cx},{cy})={ci_name} -> ({ni % w},{ni // w})={ni_name}", ct.get_id())

        # Our transport/turret at gap → don't destroy
        if ci_bld is not None and ci_bld.team == s.my_team and isinstance(ci_bld, _TRANSPORT_OR_TURRETS):
            a.source_ti = None
            return "atk:redir", False

        # Our transport/turret at next tile → don't build into
        ni_bld = s.building[ni]
        if ni_bld is not None and ni_bld.team == s.my_team and isinstance(ni_bld, _TRANSPORT_OR_TURRETS):
            a.source_ti = None
            return "atk:redir_ni", False

        # Enemy non-marker building at gap
        if ci_bld is not None and ci_bld.team != s.my_team and not isinstance(ci_bld, BuildingMarker):
            if isinstance(ci_bld, BuildingRoad):
                # Fire at enemy road
                if ci in s.danger_zones and pos != build_pos:
                    a.source_ti = None
                    return "atk:road_danger", False
                if pos == build_pos:
                    if ct.can_fire(build_pos):
                        ct.fire(build_pos)
                        return f"atk:fire({cx},{cy})", True
                    return "atk:fire_cd", False
                nav.set_goal(build_pos)
                return f"atk:walk_fire({cx},{cy})", nav.step(ct)
            else:
                # Non-road enemy: try turret at prev tile
                if prev_ti is not None:
                    turret = try_place_turret_at(s, ct, nav, prev_ti,
                        chain[k - 2] if k >= 2 else _feeder_of(flow, s, prev_ti), pos)
                    if turret is not None:
                        a.source_ti = None
                        return turret
                a.source_ti = None
                return "atk:blocked", False

        # Enemy non-marker at next tile → don't build into, try turret
        if ni_bld is not None and ni_bld.team != s.my_team and not isinstance(ni_bld, BuildingMarker):
            turret = try_place_turret_at(s, ct, nav, ci, prev_ti, pos)
            if turret is not None:
                a.source_ti = None
                return turret
            a.source_ti = None
            return "atk:blocked_ni", False

        # Danger zone → turret only
        if ci in s.danger_zones:
            turret = try_place_turret_at(s, ct, nav, ci, prev_ti, pos)
            if turret is not None:
                a.source_ti = None
                return turret
            a.source_ti = None
            return "atk:danger", False

        # Try gunner (high priority)
        gunner = try_place_turret_at(s, ct, nav, ci, prev_ti, pos, gunner_only=True)
        if gunner is not None:
            a.source_ti = None
            return gunner

        # Build conveyor
        if pos.distance_squared(build_pos) > 2:
            nav.set_goal(build_pos)
            return f"atk:walk_gap({cx},{cy})", nav.step(ct)

        nx, ny = ni % w, ni // w
        result = _build_at_gap(
            builder, ct, cx, cy, nx, ny, build_pos,
            "atk:chain", path=chain, gap_idx=k, destroy_barriers=True,
        )
        if "conv" in result[0] or "bridge" in result[0]:
            if ni not in s.danger_zones:
                a.source_ti = ni
        elif "recompute" in result[0] or "blocked" in result[0]:
            a.source_ti = None

        # If build failed, try sentinel
        if "cant_build" in result[0] or "recompute" in result[0]:
            sentinel = try_place_turret_at(s, ct, nav, ci, prev_ti, pos, sentinel_only=True)
            if sentinel is not None:
                a.source_ti = None
                return sentinel

        return result

    return None


# ── Source finding (uses flow model) ───────────────────────


def _pick_source(flow: FlowModel, s: State, pos: Position) -> int | None:
    """Find best flow source — uses flow.flow_frontier() and flow.enemy_tappable()."""
    w = s.w
    if s.en_core_pos is not None:
        ecx, ecy = s.en_core_pos.x, s.en_core_pos.y
    else:
        ecx, ecy = w - 1 - s.core_pos.x, s.h - 1 - s.core_pos.y

    def _score(ti: int) -> int:
        tx, ty = ti % w, ti // w
        return abs(tx - ecx) + abs(ty - ecy) + abs(tx - pos.x) + abs(ty - pos.y)

    best_ti: int | None = None
    best_score = 1_000_000

    # Tier 0: Flow frontier (our transport with flow outputting to buildable tile)
    for _src_ti, gap_ti in flow.flow_frontier():
        if gap_ti in s.danger_zones:
            continue
        sc = _score(gap_ti)
        if sc < best_score:
            best_score = sc
            best_ti = gap_ti

    if best_ti is not None:
        return best_ti

    # Tier 1: Enemy tappable (parasitize their flow)
    for _en_ti, out_ti in flow.enemy_tappable():
        sc = _score(out_ti)
        if sc < best_score:
            best_score = sc
            best_ti = out_ti

    if best_ti is not None:
        return best_ti

    # Tier 2: Harvester outputs (not connected econ)
    reach = s.reachable
    for hi in s.my_harvesters | s.en_harvesters:
        if hi in s.danger_zones:
            continue
        # Count existing taps
        hx, hy = hi % w, hi // w
        taps = sum(
            1 for dx, dy in DIR4_DELTA
            if s.in_bounds(hx + dx, hy + dy)
            and (hy + dy) * w + (hx + dx) not in flow.connected
            and s.building[(hy + dy) * w + (hx + dx)] is not None
            and s.building[(hy + dy) * w + (hx + dx)].team == s.my_team
            and isinstance(s.building[(hy + dy) * w + (hx + dx)], _TRANSPORT_OR_TURRETS)
        )
        if taps >= 2:
            continue
        for dx, dy in DIR4_DELTA:
            ax, ay = hx + dx, hy + dy
            if not s.in_bounds(ax, ay):
                continue
            ai = ay * w + ax
            if s.env[ai] == Environment.WALL or ai in s.danger_zones:
                continue
            if reach is not None and not reach.is_reachable_idx(ai):
                continue
            abld = s.building[ai]
            if abld is not None:
                if isinstance(abld, BuildingMarker):
                    pass
                elif isinstance(abld, BuildingRoad):
                    pass
                elif abld.team == s.my_team and isinstance(abld, _TRANSPORT_OR_TURRETS):
                    continue
                elif abld.team != s.my_team and isinstance(abld, TRANSPORT):
                    pass
                else:
                    continue
            sc = _score(ai)
            if sc < best_score:
                best_score = sc
                best_ti = ai

    return best_ti


# ── Helpers ────────────────────────────────────────────────


def _has_adjacent_harvester(s: State, ti: int) -> bool:
    """Is there a harvester (any team) cardinally adjacent to ti?"""
    w = s.w
    tx, ty = ti % w, ti // w
    for dx, dy in DIR4_DELTA:
        ax, ay = tx + dx, ty + dy
        if s.in_bounds(ax, ay):
            ai = ay * w + ax
            if ai in s.my_harvesters or ai in s.en_harvesters:
                return True
    return False


def _feeder_of(flow: FlowModel, s: State, ti: int) -> int | None:
    """Find the tile feeding this one (for turret feed direction)."""
    inputs = flow.inputs_to(ti)
    if inputs:
        return inputs[0]
    # Check for adjacent harvester
    w = s.w
    tx, ty = ti % w, ti // w
    for dx, dy in DIR4_DELTA:
        ax, ay = tx + dx, ty + dy
        if s.in_bounds(ax, ay):
            ai = ay * w + ax
            if ai in s.my_harvesters or ai in s.en_harvesters:
                return ai
    return None


def _goals(s: State) -> set[int]:
    """Chebyshev-1 neighbors of enemy core + turrets."""
    w = s.w
    enemy = s.en_core_tiles | s.en_turrets
    goals: set[int] = set()
    reach = s.reachable
    for eti in enemy:
        ex, ey = eti % w, eti // w
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = ex + dx, ey + dy
                if not s.in_bounds(nx, ny):
                    continue
                ni = ny * w + nx
                if ni in enemy or s.env[ni] == Environment.WALL:
                    continue
                if reach is not None and not reach.is_reachable_idx(ni):
                    continue
                goals.add(ni)
    return goals


def _fallback(
    builder: Builder, ct: Controller, s: State, pos: Position
) -> tuple[str, bool]:
    """Fire → harvest adjacent ore → explore toward enemy."""
    w = s.w

    # Fire at enemy building we're standing on
    if ct.get_action_cooldown() == 0:
        bid = ct.get_tile_building_id(pos)
        if bid is not None and ct.get_team(bid) != s.my_team:
            etype = ct.get_entity_type(bid)
            if etype not in (EntityType.ROAD, EntityType.MARKER) and ct.can_fire(pos):
                ct.fire(pos)
                return "atk:fire_infra", True

    # Harvest ore if right next to it
    for dx, dy in DIR4_DELTA:
        ni = (pos.y + dy) * w + (pos.x + dx)
        if ni in builder.ti_ore.positions and ni not in s.my_harvesters and ni not in s.en_harvesters:
            tgt = s.en_core_pos or Position(w - 1 - s.core_pos.x, s.h - 1 - s.core_pos.y)
            harvest = _task_harvest(builder, ct, target_pos=tgt)
            if harvest is not None:
                if "place" in harvest[0]:
                    builder._attack.source_ti = None
                return harvest
            break

    return _task_explore_enemy(builder, ct)
