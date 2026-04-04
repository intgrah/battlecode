"""RUSH: extend conveyor chain toward enemy core, place gunners.

State machine with explicit phases:
1. FIND_ORE — no harvester on enemy half → find ore, walk, place harvester
2. EXTEND_CHAIN — harvester placed, no gunner in range → route conveyors toward core
3. PLACE_GUNNER — chain endpoint in range → place gunner with LoS + feed check
4. UPGRADE_SPLITTER — gunner placed → upgrade feeding conveyor to splitter
5. DONE — gunner fed, return Wait
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from action import PlaceGunner, PlaceHarvester, PlaceSplitter
from building import (
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingGunner,
    BuildingHarvester,
    BuildingMarker,
    BuildingSplitter,
)
from cambc import Controller, Direction, Environment, Position
from marker import ClaimKind, MarkerChainPlan, MarkerClaim
from turn import ActionOnly, Turn, Wait
from util import DIR4_DELTA, DIR8, GUNNER_RANGE_SQ, INF, MIN_GUNNER_FLOW

if TYPE_CHECKING:
    from state import State

# Precomputed direction deltas (avoids d.delta() calls in hot loops)
_DIR8_DELTAS: tuple[tuple[int, int], ...] = tuple(d.delta() for d in DIR8)


def run(state: State, ct: Controller) -> Turn | None:
    """Main siege entry point — dispatches to the appropriate phase."""
    en_core = state.en_core_pos
    if en_core is None:
        return None

    pos = state.pos
    # Only rush if closer to enemy core than our core
    if pos.distance_squared(en_core) > pos.distance_squared(state.my_core):
        return None

    core_tiles = _make_core_tiles(state, en_core)

    # Phase 1: can we place a gunner right now? (flow tile in range)
    result = _try_place_gunner(state, ct, en_core, core_tiles)
    if result is not None:
        return result

    # Phase 1.5: upgrade conveyor feeding our gunner to splitter
    result = _try_upgrade_splitter(state, ct, en_core)
    if result is not None:
        return result

    # Phase 2: extend chain from existing flow toward core
    result = _try_extend_chain(state, ct, en_core, core_tiles)
    if result is not None:
        return result

    # Phase 3: find ore on enemy half and place harvester
    result = _try_find_ore(state, ct, en_core)
    if result is not None:
        return result

    return None


# ---------------------------------------------------------------------------
# Core tile helpers
# ---------------------------------------------------------------------------


def _make_core_tiles(state: State, en_core: Position) -> set[int]:
    """Precompute flat-index set of enemy core tiles (3x3)."""
    w, h = state.w, state.h
    tiles: set[int] = set()
    for cdx in range(-1, 2):
        for cdy in range(-1, 2):
            cx, cy = en_core.x + cdx, en_core.y + cdy
            if 0 <= cx < w and 0 <= cy < h:
                tiles.add(cy * w + cx)
    return tiles


def _can_hit_core_fast(
    w: int,
    h: int,
    env: list,
    building: list,
    core_tiles: set[int],
    gx: int,
    gy: int,
) -> Direction | None:
    """Fast LoS check — no feed direction filtering. For search only."""
    for k in range(8):
        ddx, ddy = _DIR8_DELTAS[k]
        x, y = gx + ddx, gy + ddy
        while 0 <= x < w and 0 <= y < h:
            if (x - gx) ** 2 + (y - gy) ** 2 > GUNNER_RANGE_SQ:
                break
            i = y * w + x
            if i in core_tiles:
                return DIR8[k]
            if env[i] == Environment.WALL:
                break
            bld = building[i]
            if bld is not None and not isinstance(bld, BuildingMarker):
                break
            x += ddx
            y += ddy
    return None


def _can_hit_core(
    state: State,
    gx: int,
    gy: int,
    en_core: Position,
    core_tiles: set[int],
) -> Direction | None:
    """Full LoS check with feed direction filtering. For placement only."""
    w, h = state.w, state.h
    feed_dir = _find_feed_direction(state, gx, gy)

    for k in range(8):
        d = DIR8[k]
        if feed_dir is not None and d == feed_dir.opposite():
            continue
        ddx, ddy = _DIR8_DELTAS[k]
        adj_x, adj_y = gx + ddx, gy + ddy
        if 0 <= adj_x < w and 0 <= adj_y < h:
            if isinstance(state.building[adj_y * w + adj_x], BuildingHarvester):
                continue
        x, y = adj_x, adj_y
        while 0 <= x < w and 0 <= y < h:
            if (x - gx) ** 2 + (y - gy) ** 2 > GUNNER_RANGE_SQ:
                break
            i = y * w + x
            if i in core_tiles:
                return d
            if state.env[i] == Environment.WALL:
                break
            bld = state.building[i]
            if bld is not None and not isinstance(bld, BuildingMarker):
                break
            x += ddx
            y += ddy
    return None


def _find_feed_direction(state: State, sx: int, sy: int) -> Direction | None:
    """Find which direction feeds tile (sx,sy) — for splitter orientation."""
    w = state.w
    for dx, dy in DIR4_DELTA:
        nx, ny = sx + dx, sy + dy
        if not state.in_bounds(nx, ny):
            continue
        ni = ny * w + nx
        nbld = state.building[ni]
        match nbld:
            case (
                BuildingConveyor(direction=d, team=team)
                | BuildingArmouredConveyor(direction=d, team=team)
            ):
                if team == state.my_team:
                    ddx, ddy = d.delta()
                    if (nx + ddx, ny + ddy) == (sx, sy):
                        from util import DELTA_TO_DIR

                        return DELTA_TO_DIR.get((-dx, -dy))
            case BuildingSplitter(direction=d, team=team):
                if team == state.my_team:
                    sdx, sdy = d.delta()
                    for odx, ody in [(sdx, sdy), (-sdy, sdx), (sdy, -sdx)]:
                        if (nx + odx, ny + ody) == (sx, sy):
                            from util import DELTA_TO_DIR

                            return DELTA_TO_DIR.get((-dx, -dy))
            case BuildingHarvester(team=team):
                from util import DELTA_TO_DIR

                return DELTA_TO_DIR.get((-dx, -dy))
    return None


# ---------------------------------------------------------------------------
# Phase 1: Try to place gunner at existing flow tile in range
# ---------------------------------------------------------------------------


def _extendable_tiles(state: State) -> list[tuple[int, int]]:
    """Find tiles where we have tappable Ti flow (free output positions)."""
    w = state.w
    f = state.flow
    result: list[tuple[int, int]] = []
    seen: set[int] = set()

    for i in state.my_harvesters:
        hx, hy = i % w, i // w
        for dx, dy in DIR4_DELTA:
            nx, ny = hx + dx, hy + dy
            if not state.in_bounds(nx, ny):
                continue
            ni = ny * w + nx
            if ni in seen:
                continue
            bld = state.building[ni]
            if bld is None or isinstance(bld, (BuildingMarker,)):
                seen.add(ni)
                result.append((nx, ny))

    for i in state.my_transport:
        if f.ti[i] < 0.01:
            continue
        bld = state.building[i]
        ix, iy = i % w, i // w
        match bld:
            case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
                ddx, ddy = d.delta()
                nx, ny = ix + ddx, iy + ddy
                if state.in_bounds(nx, ny):
                    ni = ny * w + nx
                    if ni not in seen:
                        nbld = state.building[ni]
                        if nbld is None or isinstance(nbld, BuildingMarker):
                            seen.add(ni)
                            result.append((nx, ny))
            case BuildingSplitter(direction=d):
                sdx, sdy = d.delta()
                for odx, ody in [(sdx, sdy), (-sdy, sdx), (sdy, -sdx)]:
                    nx, ny = ix + odx, iy + ody
                    if state.in_bounds(nx, ny):
                        ni = ny * w + nx
                        if ni not in seen:
                            nbld = state.building[ni]
                            if nbld is None or isinstance(nbld, BuildingMarker):
                                seen.add(ni)
                                result.append((nx, ny))
            case BuildingBridge(target=bt):
                bx, by = bt
                if state.in_bounds(bx, by):
                    ni = by * w + bx
                    if ni not in seen:
                        nbld = state.building[ni]
                        if nbld is None or isinstance(nbld, BuildingMarker):
                            seen.add(ni)
                            result.append((bx, by))

    return result


def _try_place_gunner(
    state: State,
    ct: Controller,
    en_core: Position,
    core_tiles: set[int],
) -> Turn | None:
    """Phase 1: find extendable tile in gunner range of core, place gunner."""
    from tasks._helpers import move_toward

    w, h = state.w, state.h
    env = state.env
    building = state.building
    best: tuple[int, int, Direction] | None = None
    best_dist = INF

    for tx, ty in _extendable_tiles(state):
        facing = _can_hit_core_fast(w, h, env, building, core_tiles, tx, ty)
        if facing is not None:
            dist = (tx - en_core.x) ** 2 + (ty - en_core.y) ** 2
            if dist < best_dist:
                best_dist = dist
                best = (tx, ty, facing)

    if best is None:
        return None

    gx, gy, facing = best
    gpos = Position(gx, gy)

    # Verify with full LoS (feed direction check)
    full_facing = _can_hit_core(state, gx, gy, en_core, core_tiles)
    if full_facing is not None:
        facing = full_facing

    # Flow check
    gi = gy * state.w + gx
    flow_ok = any(
        state.flow.ti[ny * state.w + nx] > MIN_GUNNER_FLOW
        for dx, dy in DIR4_DELTA
        for nx, ny in [(gx + dx, gy + dy)]
        if state.in_bounds(nx, ny)
    )
    if not flow_ok and state.flow.ti[gi] < MIN_GUNNER_FLOW:
        return None

    # Can we afford it?
    ti, _ = ct.get_global_resources()
    g_cost, _ = ct.get_gunner_cost()
    if ti < g_cost:
        return Wait()

    # Are we adjacent?
    pos = state.pos
    if pos.distance_squared(gpos) <= 2 and pos != gpos:
        return ActionOnly(PlaceGunner(gpos, facing))

    return move_toward(state, ct, gpos)


# ---------------------------------------------------------------------------
# Phase 1.5: Upgrade conveyor feeding gunner to splitter
# ---------------------------------------------------------------------------


def _try_upgrade_splitter(
    state: State,
    ct: Controller,
    en_core: Position,
) -> Turn | None:
    """Upgrade conveyors feeding our gunners to splitters for chain continuation."""
    from tasks._helpers import move_toward

    w = state.w
    for ti in state.my_turrets:
        bld = state.building[ti]
        if not isinstance(bld, BuildingGunner):
            continue
        if bld.team != state.my_team:
            continue
        tx, ty = ti % w, ti // w
        if not _on_enemy_half(state, tx, ty):
            continue
        # Check cardinal neighbors for conveyor feeding this gunner
        for dx, dy in DIR4_DELTA:
            nx, ny = tx + dx, ty + dy
            if not state.in_bounds(nx, ny):
                continue
            ni = ny * w + nx
            nbld = state.building[ni]
            match nbld:
                case BuildingConveyor(direction=d, team=team) if team == state.my_team:
                    ddx, ddy = d.delta()
                    if (nx + ddx, ny + ddy) == (tx, ty):
                        # This conveyor feeds our gunner — upgrade to splitter
                        from util import DELTA_TO_DIR

                        back_dir = DELTA_TO_DIR.get((-dx, -dy))
                        if back_dir is None:
                            continue
                        splitter_dir = back_dir.opposite()
                        s_cost, _ = ct.get_splitter_cost()
                        ti_res, _ = ct.get_global_resources()
                        if ti_res < s_cost:
                            return Wait()
                        spos = Position(nx, ny)
                        pos = state.pos
                        if pos.distance_squared(spos) <= 2 and pos != spos:
                            return ActionOnly(PlaceSplitter(spos, splitter_dir))
                        return move_toward(state, ct, spos)
    return None


# ---------------------------------------------------------------------------
# Phase 2: Extend chain from flow toward core
# ---------------------------------------------------------------------------


def _find_flow_near_core(state: State, en_core: Position) -> tuple[int, int] | None:
    """Find nearest extendable tile on enemy half."""
    best: tuple[int, int] | None = None
    best_dist = INF

    for tx, ty in _extendable_tiles(state):
        if not _on_enemy_half(state, tx, ty):
            continue
        dist = (tx - en_core.x) ** 2 + (ty - en_core.y) ** 2
        if dist < best_dist:
            best_dist = dist
            best = (tx, ty)

    return best


def _find_siege_tile(
    state: State,
    from_x: int,
    from_y: int,
    en_core: Position,
    core_tiles: set[int],
) -> tuple[int, int] | None:
    """Find closest tile to source that can hit core via LoS."""
    w, h = state.w, state.h
    env = state.env
    building = state.building
    my_team = state.my_team
    best: tuple[int, int] | None = None
    best_dist = INF

    for dx in range(-5, 6):
        for dy in range(-5, 6):
            if abs(dx) <= 1 and abs(dy) <= 1:
                continue
            cx, cy = en_core.x + dx, en_core.y + dy
            if not (0 <= cx < w and 0 <= cy < h):
                continue
            ci = cy * w + cx
            if env[ci] == Environment.WALL:
                continue
            cbld = building[ci]
            if isinstance(cbld, BuildingGunner) and cbld.team == my_team:
                continue
            dist = (from_x - cx) ** 2 + (from_y - cy) ** 2
            if dist >= best_dist:
                continue
            if _can_hit_core_fast(w, h, env, building, core_tiles, cx, cy) is not None:
                best_dist = dist
                best = (cx, cy)

    return best


def _try_extend_chain(
    state: State,
    ct: Controller,
    en_core: Position,
    core_tiles: set[int],
) -> Turn | None:
    """Phase 2: extend conveyors from existing flow toward core."""
    from tasks._helpers import move_toward

    flow_tile = _find_flow_near_core(state, en_core)
    if flow_tile is None:
        return None

    fx, fy = flow_tile
    siege = _find_siege_tile(state, fx, fy, en_core, core_tiles)
    if siege is None:
        return None

    sx, sy = siege
    if (fx, fy) == (sx, sy):
        return None

    # Claim this siege target
    state.rush_siege_target = sy * state.w + sx

    # Check if another builder claimed this target
    rnd = ct.get_current_round()
    for c in state.chain_claims:
        if isinstance(c, MarkerChainPlan) and c.tile_index == state.rush_siege_target:
            return None  # defer

    state.claim = MarkerClaim(ClaimKind.SIEGE, state.rush_siege_target, rnd)

    # TODO: use FlowAstar for proper conveyor routing
    # For now, walk toward the siege tile
    target = Position(sx, sy)
    return move_toward(state, ct, target)


# ---------------------------------------------------------------------------
# Phase 3: Find ore on enemy half
# ---------------------------------------------------------------------------


def _on_enemy_half(state: State, x: int, y: int) -> bool:
    en = state.en_core_pos
    if en is None:
        return False
    mc = state.my_core
    en_dist = (x - en.x) ** 2 + (y - en.y) ** 2
    my_dist = (x - mc.x) ** 2 + (y - mc.y) ** 2
    return en_dist < my_dist + 20


def _try_find_ore(
    state: State,
    ct: Controller,
    en_core: Position,
) -> Turn | None:
    """Phase 3: find ore on enemy half, walk to it, place harvester."""
    from tasks._helpers import move_toward

    w = state.w
    best_ore: int | None = None
    best_dist = INF

    for oi in state.ore_ti:
        if oi in state.blocked_ore:
            continue
        ox, oy = oi % w, oi // w
        if not _on_enemy_half(state, ox, oy):
            continue
        # Skip ore with harvester already
        bld = state.building[oi]
        if isinstance(bld, BuildingHarvester):
            continue
        # Skip ore with non-removable buildings
        if bld is not None and not isinstance(bld, (BuildingMarker,)):
            state.blocked_ore.add(oi)
            continue
        dist = (state.pos.x - ox) ** 2 + (state.pos.y - oy) ** 2
        if dist < best_dist:
            best_dist = dist
            best_ore = oi

    if best_ore is None:
        return None

    ox, oy = best_ore % w, best_ore // w
    ore_pos = Position(ox, oy)

    # Adjacent? Place harvester.
    pos = state.pos
    if pos.distance_squared(ore_pos) <= 2 and pos != ore_pos:
        h_cost, _ = ct.get_harvester_cost()
        ti, _ = ct.get_global_resources()
        if ti < h_cost:
            return Wait()
        if ct.can_build_harvester(ore_pos):
            return ActionOnly(PlaceHarvester(ore_pos))
        state.blocked_ore.add(best_ore)
        return None

    # Walk toward a free tile adjacent to the ore
    for dx, dy in DIR4_DELTA:
        nx, ny = ox + dx, oy + dy
        if state.in_bounds(nx, ny):
            ni = ny * w + nx
            env = state.env[ni]
            if env != Environment.WALL:
                bld = state.building[ni]
                if bld is None or isinstance(bld, (BuildingMarker,)):
                    return move_toward(state, ct, Position(nx, ny))

    state.blocked_ore.add(best_ore)
    return None
