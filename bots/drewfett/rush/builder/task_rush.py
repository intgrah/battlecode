"""Siege enemy core by getting Ti flow within gunner range.

Priority:
1. If flow exists within gunner range of core → place gunner
2. If flow exists near enemy but not in range → extend chain toward core
3. If no flow near enemy → find ore, place harvester
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingGunner,
    BuildingHarvester,
    BuildingMarker,
    BuildingRoad,
    BuildingSentinel,
    BuildingSplitter,
)
from cambc import Controller, Direction, Environment, Position
from flow_astar import FlowAstar
from util import DIR4_DELTA, INF, Symmetry

from .action import Action, Fire, PlaceGunner, PlaceHarvester
from .helpers import move_toward_with_road, step_off_and_build
from .task_connect_excess import SearchKind, _already_connected, _build_action

if TYPE_CHECKING:
    from .state import State

_GUNNER_RANGE_SQ = 13
_SENTINEL_RANGE_SQ = 32
_ENEMY_HALF_SLACK = 20  # allow tiles slightly on our side (d² slack)

# Precomputed: for each (dx, dy) offset from a target, which Direction a gunner/sentinel
# must face to hit the target. Only works on exact 8-direction axes.
# Key: (dx, dy) = gunner position relative to target. Value: facing Direction.
_GUNNER_HITS: dict[tuple[int, int], Direction] = {}
_SENTINEL_HITS: dict[tuple[int, int], Direction] = {}

for _d in (
    Direction.NORTH,
    Direction.NORTHEAST,
    Direction.EAST,
    Direction.SOUTHEAST,
    Direction.SOUTH,
    Direction.SOUTHWEST,
    Direction.WEST,
    Direction.NORTHWEST,
):
    _ddx, _ddy = _d.delta()
    _x, _y = _ddx, _ddy
    while _x * _x + _y * _y <= _SENTINEL_RANGE_SQ:
        if _x * _x + _y * _y <= _GUNNER_RANGE_SQ:
            _GUNNER_HITS[(-_x, -_y)] = _d
        _SENTINEL_HITS[(-_x, -_y)] = _d
        # Sentinel has ±1 king-move arc
        for _adx in range(-1, 2):
            for _ady in range(-1, 2):
                ax, ay = -_x + _adx, -_y + _ady
                if ax * ax + ay * ay <= _SENTINEL_RANGE_SQ:
                    if (ax, ay) not in _SENTINEL_HITS:
                        _SENTINEL_HITS[(ax, ay)] = _d
        _x += _ddx
        _y += _ddy

# Sentinel-only offsets: positions sentinel can hit but gunner can't
_SENTINEL_ONLY_HITS: dict[tuple[int, int], Direction] = {
    k: v for k, v in _SENTINEL_HITS.items() if k not in _GUNNER_HITS
}


def _on_enemy_half(state: State, x: int, y: int) -> bool:
    """Is (x,y) roughly on the enemy half? Allows some slack past midline."""
    en = state.en_core_pos
    if en is None:
        return False
    mc = state.my_core
    en_dist = (x - en.x) ** 2 + (y - en.y) ** 2
    my_dist = (x - mc.x) ** 2 + (y - mc.y) ** 2
    return en_dist < my_dist + _ENEMY_HALF_SLACK


def _log(msg: str) -> None:
    pass


def _move_or_none(
    state: State,
    ct: Controller,
    target: Position,
) -> tuple[Direction, Action | None] | None:
    """Like move_toward_with_road but returns None if no progress."""
    result = move_toward_with_road(state, ct, target)
    move, build = result
    if move == Direction.CENTRE and build is None:
        return None
    return result


def rush(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    en_core = state.en_core_pos
    if en_core is None:
        _log("no enemy core known, skip")
        return None

    pos = state.pos

    # Only rush if roughly on enemy half (with slack for provisional core)
    my_dist = pos.distance_squared(en_core)
    home_dist = pos.distance_squared(state.my_core)
    if my_dist > home_dist + _ENEMY_HALF_SLACK:
        return None

    w = state.w
    f = state.flow

    ext_tiles = _extendable_tiles(state)
    t = ct.get_cpu_time_elapsed

    # Build set of all enemy building indices for O(1) lookup
    en_buildings = (
        state.en_turrets
        | state.en_harvesters
        | state.en_transport
        | state.en_core_tiles
        | state.en_barriers
    )

    # Step 1: Can any extendable tile hit an enemy? Place gunner.
    # Uses precomputed offset table — 20 lookups per ext tile, no ray casting.
    if ext_tiles and en_buildings:
        for ex, ey in ext_tiles:
            for (dx, dy), facing in _GUNNER_HITS.items():
                tx, ty = ex + dx, ey + dy
                if not state.in_bounds(tx, ty):
                    continue
                ti = ty * w + tx
                if ti not in en_buildings:
                    continue
                if _los_clear(state, ex, ey, facing, tx, ty):
                    feed_dir = _find_splitter_dir(state, ex, ey)
                    if feed_dir is not None and facing == feed_dir.opposite():
                        continue
                    result = _place_gunner_at(state, ct, Position(ex, ey), facing)
                    if result is not None:
                        return result
    # Step 1b: Sentinel — high-value targets only (turrets, core, harvesters)
    sentinel_targets = state.en_turrets | state.en_core_tiles | state.en_harvesters
    if ext_tiles and sentinel_targets:
        ext_set = {ey * w + ex for ex, ey in ext_tiles}
        for ti in sentinel_targets:
            tx, ty = ti % w, ti // w
            for (dx, dy), facing in _SENTINEL_HITS.items():
                gx, gy = tx + dx, ty + dy
                if not state.in_bounds(gx, gy):
                    continue
                gi = gy * w + gx
                if gi not in ext_set:
                    continue
                if (dx, dy) in _GUNNER_HITS and _los_clear(
                    state, gx, gy, _GUNNER_HITS[(dx, dy)], tx, ty
                ):
                    continue
                feed_dir = _find_splitter_dir(state, gx, gy)
                if feed_dir is not None and facing == feed_dir.opposite():
                    continue
                result = _place_sentinel_at(state, ct, Position(gx, gy), facing)
                if result is not None:
                    return result

    # Step 1.5: Upgrade conveyors feeding our gunners to splitters
    if ext_tiles:
        result = _upgrade_to_splitter(state, ct, en_core)
        if result is not None:
            return result

    # Step 2: Any tile with our flow near enemy core? → extend toward core
    flow_tile = None
    if ext_tiles:
        flow_tile = _find_flow_near_core(state, en_core, ext_tiles)
    if flow_tile is not None:
        fx, fy = flow_tile
        flow_dist = (fx - en_core.x) ** 2 + (fy - en_core.y) ** 2
        t()
        siege = _find_siege_tile_fast(state, fx, fy, en_core.x, en_core.y)
        if siege is not None and siege != (fx, fy):
            result = _extend_from_flow(state, ct, fx, fy, en_core)
            if result is not None:
                return result
        _log(
            f"step2: flow at ({fx},{fy}) d²={flow_dist} but no further siege tile (siege={siege})"
        )
        # Flow is as close as we can get but can't hit core — need different angle
        # Try extending from a different flow tile
    else:
        _log("step2: no flow tile near enemy core")

    # Step 2.5: Unconnected harvester near core — build first conveyor toward siege
    t()
    for hi in state.my_harvesters:
        hx, hy = hi % w, hi // w
        h_dist = (hx - en_core.x) ** 2 + (hy - en_core.y) ** 2
        if _on_enemy_half(state, hx, hy):
            flow_val = f.ti[hi]
            if flow_val < 0.01:
                has_flow = False
                for dx, dy in DIR4_DELTA:
                    ni = (hy + dy) * w + (hx + dx)
                    if 0 <= hx + dx < w and 0 <= hy + dy < state.h and f.ti[ni] > 0:
                        has_flow = True
                        break
                if not has_flow:
                    _log(
                        f"step2.5: harvester ({hx},{hy}) d²={h_dist} flow={flow_val:.3f} unconnected"
                    )
                    # Build first conveyor from harvester toward siege ourselves
                    tap = _find_free_adjacent(state, hx, hy)
                    if tap is not None:
                        t()
                        siege = _find_siege_tile_fast(
                            state, tap[0], tap[1], en_core.x, en_core.y
                        )
                        if siege is not None:
                            _log(
                                f"step2.5: tap=({tap[0]},{tap[1]}), building toward siege ({siege[0]},{siege[1]})"
                            )
                            return _extend_from_flow(state, ct, tap[0], tap[1], en_core)
                        _log(
                            f"step2.5: tap=({tap[0]},{tap[1]}) but no siege tile found"
                        )
                    else:
                        _log(f"step2.5: no free adjacent to harvester ({hx},{hy})")
                    _log(
                        f"step2.5: unconnected harvester at ({hx},{hy}), no siege path"
                    )
                    continue
                _log(
                    f"step2.5: harvester ({hx},{hy}) d²={h_dist} flow={flow_val:.3f} has adjacent flow, skip"
                )
            else:
                _log(
                    f"step2.5: harvester ({hx},{hy}) d²={h_dist} has flow={flow_val:.3f}, skip"
                )

    # Step 3: No flow on enemy half — find ore on enemy half or walk toward core
    source = _find_rush_ore(state, en_core)
    if source is not None:
        kind, ore_idx, tap_x, tap_y = source
        # Livelock detection: if stuck on same target for 30 turns, block it
        if ore_idx == state.rush_target_idx:
            state.rush_target_turns += 1
            if state.rush_target_turns > 30:
                state.blocked_ore[ore_idx] = state.age + state.birthday
                state.rush_target_idx = None
                state.rush_target_turns = 0
                return None
        else:
            state.rush_target_idx = ore_idx
            state.rush_target_turns = 0
        ore_pos = Position(ore_idx % w, ore_idx // w)
        _log(f"step3: {kind} ore at ({ore_pos.x},{ore_pos.y})")
        if kind == "free":
            if pos.distance_squared(ore_pos) <= 2 and pos != ore_pos:
                # Don't place if enemy transport adjacent — would steal output
                from .task_harvest_ti import _adjacent_safe_for_harvester

                if not _adjacent_safe_for_harvester(state, ore_pos.x, ore_pos.y):
                    state.blocked_ore[ore_idx] = state.age + state.birthday
                    return None  # skip, scout will find other ore
                h_cost, _ = ct.get_harvester_cost()
                ti, _ = ct.get_global_resources()
                if ti < h_cost:
                    return Direction.CENTRE, None  # Wait for Ti
                # Destroy our road/barrier on ore if present
                bid = (
                    ct.get_tile_building_id(ore_pos)
                    if ct.is_in_vision(ore_pos)
                    else None
                )
                if (
                    bid is not None
                    and ct.get_team(bid) == state.my_team
                    and ct.can_destroy(ore_pos)
                ):
                    ct.destroy(ore_pos)
                if ct.can_build_harvester(ore_pos):
                    return Direction.CENTRE, PlaceHarvester(ore_pos)
                state.blocked_ore[ore_idx] = state.age + state.birthday
            if pos.distance_squared(ore_pos) > 2:
                # Walk to the tap point (free adjacent tile), not the ore itself
                tap_pos = Position(tap_x, tap_y)
                _log(
                    f"step3: walking toward tap ({tap_x},{tap_y}) for ore ({ore_pos.x},{ore_pos.y})"
                )
                return _move_or_none(state, ct, tap_pos)
        # ours/parasite — extend from tap
        siege = _find_siege_tile_fast(state, tap_x, tap_y, en_core.x, en_core.y)
        if siege is not None:
            _log(f"step3: extending from tap ({tap_x},{tap_y})")
            return _extend_from_flow(state, ct, tap_x, tap_y, en_core)

    # Nothing useful — defer to explore
    return None


_DIR8 = [
    Direction.NORTH,
    Direction.NORTHEAST,
    Direction.EAST,
    Direction.SOUTHEAST,
    Direction.SOUTH,
    Direction.SOUTHWEST,
    Direction.WEST,
    Direction.NORTHWEST,
]

# Precomputed deltas for the 8 directions (avoids repeated d.delta() calls)
_DIR8_DELTAS: tuple[tuple[int, int], ...] = (
    (0, -1),
    (1, -1),
    (1, 0),
    (1, 1),
    (0, 1),
    (-1, 1),
    (-1, 0),
    (-1, -1),
)


def _los_clear(
    state: State,
    gx: int,
    gy: int,
    facing: Direction,
    tx: int,
    ty: int,
) -> bool:
    """Check LoS from gunner at (gx,gy) facing `facing` to (tx,ty)."""
    w, h = state.w, state.h
    ddx, ddy = facing.delta()
    x, y = gx + ddx, gy + ddy
    while 0 <= x < w and 0 <= y < h:
        if (x - gx) ** 2 + (y - gy) ** 2 > _GUNNER_RANGE_SQ:
            return False
        if x == tx and y == ty:
            return True
        env = state.env[y * w + x]
        if env == Environment.WALL:
            return False
        bld = state.building[y * w + x]
        if bld is not None and not isinstance(bld, BuildingMarker):
            return False
        x += ddx
        y += ddy
    return False


def _place_sentinel_at(
    state: State,
    ct: Controller,
    at: Position,
    facing: Direction,
) -> tuple[Direction, Action | None] | None:
    """Place sentinel at a tile."""
    from .action import PlaceSentinel

    s_cost, _ = ct.get_sentinel_cost()
    ti, _ = ct.get_global_resources()
    if ti < s_cost:
        return None
    pos = state.pos
    w = state.w
    ni = at.y * w + at.x
    bld = state.building[ni]
    # Already has our sentinel
    if isinstance(bld, BuildingSentinel) and bld.team == state.my_team:
        return None
    # Enemy building — clear it
    if (
        bld is not None
        and bld.team != state.my_team
        and not isinstance(bld, BuildingMarker)
    ):
        if pos == at:
            return Direction.CENTRE, Fire()
        return _move_or_none(state, ct, at)
    # Build
    if pos == at:
        return step_off_and_build(ct, PlaceSentinel(at, facing))
    if pos.distance_squared(at) <= 2:
        if bld is not None and bld.team == state.my_team and ct.can_destroy(at):
            ct.destroy(at)
        if ct.can_build_sentinel(at, facing):
            return Direction.CENTRE, PlaceSentinel(at, facing)
    return _move_or_none(state, ct, at)


def _find_siege_tile_fast(
    state: State,
    from_x: int,
    from_y: int,
    target_x: int,
    target_y: int,
) -> tuple[int, int] | None:
    """Find closest buildable tile to (from_x,from_y) that can hit (target_x,target_y).
    Uses precomputed _GUNNER_HITS table instead of 112-tile LoS scan."""
    w, h = state.w, state.h
    best: tuple[int, int] | None = None
    best_dist = INF
    my_team = state.my_team

    for (dx, dy), facing in _GUNNER_HITS.items():
        gx, gy = target_x + dx, target_y + dy
        if not (0 <= gx < w and 0 <= gy < h):
            continue
        gi = gy * w + gx
        env = state.env[gi]
        if env == Environment.WALL:
            continue
        bld = state.building[gi]
        if isinstance(bld, BuildingGunner) and bld.team == my_team:
            continue
        dist = (from_x - gx) ** 2 + (from_y - gy) ** 2
        if dist >= best_dist:
            continue
        if _los_clear(state, gx, gy, facing, target_x, target_y):
            best_dist = dist
            best = (gx, gy)

    return best


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
    """Fast LoS check — no feed direction filtering.

    Use this for search. Check feed direction only at actual placement.
    """
    for k in range(8):
        ddx, ddy = _DIR8_DELTAS[k]
        x, y = gx + ddx, gy + ddy
        while 0 <= x < w and 0 <= y < h:
            if (x - gx) ** 2 + (y - gy) ** 2 > _GUNNER_RANGE_SQ:
                break
            i = y * w + x
            if i in core_tiles:
                return _DIR8[k]
            if env[i] == Environment.WALL:
                break
            bld = building[i]
            if bld is not None and not isinstance(bld, BuildingMarker):
                break
            x += ddx
            y += ddy
    return None


def _can_hit_core(
    state: State, gx: int, gy: int, en_core: Position
) -> Direction | None:
    """Full LoS check with feed direction filtering. Use at placement time."""
    w, h = state.w, state.h
    core_tiles = _make_core_tiles(state, en_core)
    feed_dir = _find_splitter_dir(state, gx, gy)

    for k in range(8):
        d = _DIR8[k]
        if feed_dir is not None and d == feed_dir.opposite():
            continue
        ddx, ddy = _DIR8_DELTAS[k]
        adj_x, adj_y = gx + ddx, gy + ddy
        if 0 <= adj_x < w and 0 <= adj_y < h:
            if isinstance(state.building[adj_y * w + adj_x], BuildingHarvester):
                continue
        x, y = adj_x, adj_y
        while 0 <= x < w and 0 <= y < h:
            if (x - gx) ** 2 + (y - gy) ** 2 > _GUNNER_RANGE_SQ:
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


def _extendable_tiles(state: State) -> list[tuple[int, int]]:
    """Find tiles where we have real, tappable Ti flow.

    Valid sources:
    1. Free tile adjacent to our harvester (harvester outputs all 4 sides)
    2. Free tile a conveyor with flow points at
    3. Free tile a splitter with flow outputs to (forward/left/right)
    4. Bridge target tile (bridge delivers there)
    """
    w = state.w
    f = state.flow
    result: list[tuple[int, int]] = []
    seen: set[int] = set()

    for i in state.my_harvesters:
        # Skip harvesters whose flow is fully committed to gunners
        available = 0.25 - f.gunners_fed[i]
        _log(
            f"extendable: harv ({i % w},{i // w}) gunners_fed={f.gunners_fed[i]:.2f} avail={available:.3f}"
        )
        if available < 0.1:
            continue
        hx, hy = i % w, i // w
        for dx, dy in DIR4_DELTA:
            nx, ny = hx + dx, hy + dy
            if not state.in_bounds(nx, ny):
                continue
            ni = ny * w + nx
            if ni in seen:
                continue
            bld = state.building[ni]
            if bld is None or isinstance(bld, (BuildingRoad, BuildingMarker)):
                seen.add(ni)
                result.append((nx, ny))

    for i in state.my_transport:
        available = f.ti[i] - f.gunners_fed[i]
        if available < 0.1:
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
                        if nbld is None or isinstance(
                            nbld, (BuildingRoad, BuildingMarker)
                        ):
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
                            if nbld is None or isinstance(
                                nbld, (BuildingRoad, BuildingMarker)
                            ):
                                seen.add(ni)
                                result.append((nx, ny))
            case BuildingBridge(target=bt):
                bx, by = bt
                if state.in_bounds(bx, by):
                    ni = by * w + bx
                    if ni not in seen:
                        nbld = state.building[ni]
                        if nbld is None or isinstance(
                            nbld, (BuildingRoad, BuildingMarker)
                        ):
                            seen.add(ni)
                            result.append((bx, by))
    return result


def _find_splitter_dir(state: State, sx: int, sy: int) -> Direction | None:
    """Find the correct splitter direction for a tile based on what feeds it.

    Splitter accepts from back only. Find which neighbor feeds into (sx,sy)
    and face the splitter AWAY from that input (so back faces the input).
    """
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
            ) if team == state.my_team:
                ddx, ddy = d.delta()
                if (nx + ddx, ny + ddy) == (sx, sy):
                    # This neighbor feeds us. Face away from it.
                    # Input comes from direction (dx, dy) relative to us
                    # Splitter faces opposite = (-dx, -dy) direction
                    from util import DELTA_TO_DIR

                    return DELTA_TO_DIR.get((-dx, -dy))
            case BuildingHarvester():
                # Harvester outputs to all cardinal neighbors
                from util import DELTA_TO_DIR

                return DELTA_TO_DIR.get((-dx, -dy))
            case BuildingSplitter(direction=d, team=team) if team == state.my_team:
                sdx, sdy = d.delta()
                for odx, ody in [(sdx, sdy), (-sdy, sdx), (sdy, -sdx)]:
                    if (nx + odx, ny + ody) == (sx, sy):
                        from util import DELTA_TO_DIR

                        return DELTA_TO_DIR.get((-dx, -dy))
    return None


def _upgrade_to_splitter(
    state: State,
    ct: Controller,
    en_core: Position,
) -> tuple[Direction, Action | None] | None:
    """Replace conveyors feeding our gunners with splitters.

    This lets the chain continue extending past the gunner via the
    splitter's side outputs.
    """
    from .action import PlaceSplitter

    w = state.w
    pos = state.pos

    for ti in state.my_turrets:
        bld = state.building[ti]
        if not isinstance(bld, BuildingGunner) or bld.team != state.my_team:
            continue
        if not _on_enemy_half(state, ti % w, ti // w):
            continue
        tx, ty = ti % w, ti // w

        # Check cardinal neighbors for a conveyor feeding this gunner
        for dx, dy in DIR4_DELTA:
            nx, ny = tx + dx, ty + dy
            if not state.in_bounds(nx, ny):
                continue
            ni = ny * w + nx
            nbld = state.building[ni]
            match nbld:
                case BuildingConveyor(direction=d, team=team) if team == state.my_team:
                    # Check if this conveyor points at the gunner
                    ddx, ddy = d.delta()
                    if (nx + ddx, ny + ddy) == (tx, ty):
                        # Already a splitter? Skip
                        if isinstance(nbld, BuildingSplitter):
                            continue
                        # Find what feeds INTO this conveyor to orient the splitter
                        # Splitter back must face the input source
                        sp_dir = _find_splitter_dir(state, nx, ny)
                        if sp_dir is None:
                            continue
                        sp_cost, _ = ct.get_splitter_cost()
                        ti_res, _ = ct.get_global_resources()
                        if ti_res < sp_cost:
                            continue
                        conv_pos = Position(nx, ny)
                        if pos.distance_squared(conv_pos) <= 2:
                            if ct.can_destroy(conv_pos):
                                ct.destroy(conv_pos)
                            if ct.can_build_splitter(conv_pos, sp_dir):
                                _log(
                                    f"step1.5: upgrading conveyor at ({nx},{ny}) to splitter facing {sp_dir.name}"
                                )
                                return Direction.CENTRE, PlaceSplitter(conv_pos, sp_dir)
                        return _move_or_none(state, ct, conv_pos)

    return None


def _find_flow_in_range(
    state: State,
    en_core: Position,
    ext_tiles: list[tuple[int, int]] | None = None,
) -> tuple[int, int, Direction] | None:
    """Find a tile with tappable flow that can hit enemy core via LoS ray."""
    best: tuple[int, int, Direction] | None = None
    best_dist = INF

    w, h = state.w, state.h
    env = state.env
    building = state.building
    ct = _make_core_tiles(state, en_core)

    for tx, ty in ext_tiles if ext_tiles is not None else _extendable_tiles(state):
        facing = _can_hit_core_fast(w, h, env, building, ct, tx, ty)
        if facing is not None:
            dist = (tx - en_core.x) ** 2 + (ty - en_core.y) ** 2
            if dist < best_dist:
                best_dist = dist
                best = (tx, ty, facing)

    return best


def _find_flow_near_core(
    state: State,
    en_core: Position,
    ext_tiles: list[tuple[int, int]] | None = None,
) -> tuple[int, int] | None:
    """Find nearest extendable free tile on the enemy half."""
    best: tuple[int, int] | None = None
    best_dist = INF

    for tx, ty in ext_tiles if ext_tiles is not None else _extendable_tiles(state):
        if not _on_enemy_half(state, tx, ty):
            continue
        dist = (tx - en_core.x) ** 2 + (ty - en_core.y) ** 2
        if dist < best_dist:
            best_dist = dist
            best = (tx, ty)

    return best


def _extend_from_flow(
    state: State,
    ct: Controller,
    flow_x: int,
    flow_y: int,
    en_core: Position,
) -> tuple[Direction, Action | None] | None:
    """Extend conveyor chain from a flow tile toward enemy core."""
    w = state.w
    pos = state.pos

    _log(f"extend: from ({flow_x},{flow_y}) toward core ({en_core.x},{en_core.y})")

    # Cache siege target — only recompute when flow source changes
    flow_idx = flow_y * w + flow_x
    if state.rush_cached_siege is not None and state.rush_siege_target == flow_idx:
        siege_idx = state.rush_cached_siege
        siege_x, siege_y = siege_idx % w, siege_idx // w
    else:
        siege = _find_siege_tile_fast(state, flow_x, flow_y, en_core.x, en_core.y)
        if siege is None:
            state.rush_cached_siege = None
            return None
        siege_x, siege_y = siege
        siege_idx = siege_y * w + siege_x
        state.rush_cached_siege = siege_idx
        state.rush_siege_target = flow_idx

    # FlowAstar — resume cached search or start new one
    if state.rush_flow_search is not None and state.rush_flow_source == flow_idx:
        search = state.rush_flow_search
    else:
        search = FlowAstar(
            state, flow_x, flow_y, {siege_idx}, 0, hx=siege_x, hy=siege_y
        )
        state.rush_flow_source = flow_idx
    path = search.compute(lambda: ct.get_cpu_time_elapsed() < 800)
    state.rush_flow_search = None if search.exhausted else search
    if path is not None:
        coords = [(p % w, p // w) for p in path]
        _log(f"extend: path={coords}")
    if path is None or len(path) < 2:
        _log(
            f"extend: FlowAstar failed from ({flow_x},{flow_y}) to ({siege_x},{siege_y}), path={'None' if path is None else len(path)}"
        )
        return None

    _log(f"extend: path len={len(path)}, builder at ({pos.x},{pos.y})")

    # Build along path
    for k in range(len(path) - 1):
        x, y = path[k] % w, path[k] // w
        nx, ny = path[k + 1] % w, path[k + 1] // w
        idx = path[k]

        connected = _already_connected(state, idx, x, y, nx, ny, SearchKind.MIXED)
        bld = state.building[idx]
        bld_name = type(bld).__name__ if bld is not None else "None"
        bld_team = getattr(bld, "team", None)
        _log(
            f"extend[{k}]: ({x},{y})->({nx},{ny}) bld={bld_name} team={bld_team} connected={connected}"
        )

        if connected:
            _log(f"extend[{k}]: already connected, skip")
            continue

        build_at = Position(x, y)
        next_pos = Position(nx, ny)
        builder_dist = pos.distance_squared(build_at)

        # Check 2 tiles ahead — if enemy building at path[k+2], place gunner at path[k+1]
        # This lets the conveyor chain extend to path[k], gunner at path[k+1] clears path[k+2]
        if k + 2 < len(path):
            ahead2_idx = path[k + 2]
            ahead2_bld = state.building[ahead2_idx]
            if (
                ahead2_bld is not None
                and ahead2_bld.team != state.my_team
                and not isinstance(ahead2_bld, (BuildingMarker, BuildingHarvester))
            ):
                ahead2_x, ahead2_y = ahead2_idx % w, ahead2_idx // w
                ahead2_name = type(ahead2_bld).__name__
                # Build conveyor at path[k] normally, THEN place gunner at path[k+1]
                # If path[k] already has our conveyor, go place gunner at path[k+1]
                if not connected:
                    # First build conveyor here
                    _log(
                        f"extend[{k}]: enemy {ahead2_name} at ({ahead2_x},{ahead2_y}) 2 ahead, building conveyor at ({x},{y}) first"
                    )
                else:
                    # Conveyor done, place gunner at path[k+1] facing path[k+2]
                    gunner_facing = next_pos.direction_to(Position(ahead2_x, ahead2_y))
                    feed_dir2 = _find_splitter_dir(state, nx, ny)
                    if feed_dir2 is not None and gunner_facing == feed_dir2.opposite():
                        _log(
                            f"extend[{k}]: gunner at ({nx},{ny}) would face feed, skip"
                        )
                    elif gunner_facing != Direction.CENTRE and _los_clear(
                        state, nx, ny, gunner_facing, ahead2_x, ahead2_y
                    ):
                        _log(
                            f"extend[{k}]: placing gunner at ({nx},{ny}) facing ({ahead2_x},{ahead2_y}) to clear"
                        )
                        result = _place_gunner_at(state, ct, next_pos, gunner_facing)
                        if result is not None:
                            return result
                        _log(f"extend[{k}]: can't afford gunner, holding turn")
                        return None

        # Check what's on the NEXT tile — if enemy building, place gunner HERE to clear it
        # (fallback for when we can't look 2 ahead, e.g. last tiles in path)
        next_idx = path[k + 1]
        next_bld = state.building[next_idx]
        if (
            next_bld is not None
            and next_bld.team != state.my_team
            and not isinstance(next_bld, (BuildingMarker, BuildingHarvester))
        ):
            next_name = type(next_bld).__name__
            facing = build_at.direction_to(next_pos)
            # Don't face toward our feed source
            feed_dir = _find_splitter_dir(state, x, y)
            if feed_dir is not None and facing == feed_dir.opposite():
                _log(f"extend[{k}]: enemy ahead but facing would block feed, skip")
            elif facing != Direction.CENTRE and _los_clear(state, x, y, facing, nx, ny):
                _log(
                    f"extend[{k}]: enemy {next_name} ahead at ({nx},{ny}), placing gunner at ({x},{y}) facing {facing.name}"
                )
                result = _place_gunner_at(state, ct, build_at, facing)
                if result is not None:
                    return result
                _log(f"extend[{k}]: can't afford gunner, holding turn")
                return None
            _log(f"extend[{k}]: enemy ahead but CENTRE facing, skip")

        # Enemy building on THIS tile (not marker) — walk on and fire
        if (
            bld is not None
            and bld.team != state.my_team
            and not isinstance(bld, BuildingMarker)
        ):
            _log(f"extend[{k}]: enemy {bld_name} at ({x},{y}), need to fire")
            if pos == build_at:
                _log(f"extend[{k}]: on tile, firing")
                return Direction.CENTRE, Fire()
            if builder_dist <= 2:
                d = pos.direction_to(build_at)
                if ct.can_move(d):
                    _log(f"extend[{k}]: adjacent, moving {d.name} to fire")
                    return d, None
                _log(f"extend[{k}]: adjacent but can't move {d.name}")
            _log(f"extend[{k}]: walking toward enemy at ({x},{y}) d²={builder_dist}")
            return _move_or_none(state, ct, build_at)

        # If this tile can already hit core, place gunner instead of conveyor
        hit_facing = _can_hit_core(state, x, y, en_core)
        if hit_facing is not None:
            _log(
                f"extend[{k}]: ({x},{y}) can hit core facing {hit_facing.name}, placing gunner"
            )
            result = _place_gunner_at(state, ct, build_at, hit_facing)
            if result is not None:
                return result
            # Can't afford gunner — hold the turn so nothing else runs
            _log(f"extend[{k}]: can't afford gunner, holding turn")
            return None

        # Sentinel mid-chain: HVT (turrets, core, harvesters) in sentinel range
        hvt = state.en_turrets | state.en_core_tiles | state.en_harvesters
        for (sdx, sdy), sfacing in _SENTINEL_HITS.items():
            etx, ety = x + sdx, y + sdy
            if not state.in_bounds(etx, ety):
                continue
            eti = ety * w + etx
            if eti not in hvt:
                continue
            if (sdx, sdy) in _GUNNER_HITS:
                continue
            feed_dir = _find_splitter_dir(state, x, y)
            if feed_dir is not None and sfacing == feed_dir.opposite():
                continue
            _log(f"extend[{k}]: ({x},{y}) sentinel can hit HVT at ({etx},{ety})")
            result = _place_sentinel_at(state, ct, build_at, sfacing)
            if result is not None:
                return result
            break

        # Build conveyor
        action = _build_action(build_at, nx, ny, SearchKind.MIXED)
        if builder_dist <= 2:
            if (
                bld is not None
                and bld.team == state.my_team
                and ct.can_destroy(build_at)
            ):
                _log(
                    f"extend[{k}]: destroying allied {bld_name} at ({x},{y}) to rebuild"
                )
                ct.destroy(build_at)
            # Build and step toward next tile if possible
            step = pos.direction_to(build_at)
            _log(
                f"extend[{k}]: building ({x},{y})->({nx},{ny}) action={action} step={step.name}"
            )
            return step, action
        _log(f"extend[{k}]: need to walk to ({x},{y}) d²={builder_dist}")
        return _move_or_none(state, ct, build_at)

    # All conveyors built — place gunner at siege endpoint
    last = path[-1]
    lx, ly = last % w, last // w
    last_bld = state.building[last]
    # Already have our gunner here — done, try upgrading to splitter
    if isinstance(last_bld, BuildingGunner) and last_bld.team == state.my_team:
        _log(f"extend: endpoint ({lx},{ly}) already has our gunner")
        return _upgrade_to_splitter(state, ct, en_core)

    facing = _can_hit_core(state, lx, ly, en_core)
    _log(
        f"extend: all conveyors done, endpoint ({lx},{ly}) facing={facing.name if facing else 'None'}"
    )
    if facing is not None:
        _log(f"extend: endpoint ({lx},{ly}) placing gunner facing {facing.name}")
        result = _place_gunner_at(state, ct, Position(lx, ly), facing)
        if result is not None:
            return result
        _log("extend: can't afford gunner, holding turn")
        return None

    _log(f"extend: endpoint ({lx},{ly}) cannot hit core, returning None")
    return None


def _place_gunner_at(
    state: State,
    ct: Controller,
    at: Position,
    facing: Direction,
) -> tuple[Direction, Action | None] | None:
    """Place gunner at a tile with verified LoS facing."""
    g_cost, _ = ct.get_gunner_cost()
    ti, _ = ct.get_global_resources()
    _log(
        f"gunner: want to place at ({at.x},{at.y}) facing {facing.name}, ti={ti} cost={g_cost}"
    )
    if ti < g_cost:
        _log(f"gunner: cannot afford (need {g_cost}, have {ti})")
        return None

    # Flow check: will this gunner have ammo?
    # Check feeding tile's flow minus what existing gunners already consume
    pos = state.pos
    w = state.w
    ni = at.y * w + at.x
    best_available = 0.0
    for dx, dy in DIR4_DELTA:
        nx, ny = at.x + dx, at.y + dy
        if not state.in_bounds(nx, ny):
            continue
        fi = ny * w + nx
        flow = state.flow.ti[fi]
        committed = state.flow.gunners_fed[fi]
        available = flow - committed
        best_available = max(best_available, available)
    # Also check the tile itself
    flow = state.flow.ti[ni]
    committed = state.flow.gunners_fed[ni]
    best_available = max(best_available, flow - committed)
    if best_available < 0.1:
        _log(
            f"gunner: insufficient available flow {best_available:.3f} at ({at.x},{at.y})"
        )
        return None

    bld = state.building[ni]
    bld_name = type(bld).__name__ if bld is not None else "None"
    bld_team = getattr(bld, "team", None)
    builder_dist = pos.distance_squared(at)
    _log(
        f"gunner: target ({at.x},{at.y}) bld={bld_name} team={bld_team} builder=({pos.x},{pos.y}) d²={builder_dist}"
    )

    # Already has our gunner
    if isinstance(bld, BuildingGunner) and bld.team == state.my_team:
        _log(f"gunner: already have our gunner at ({at.x},{at.y}), done")
        return None

    # Enemy building on target — walk on and fire to clear
    if (
        bld is not None
        and bld.team != state.my_team
        and not isinstance(bld, BuildingMarker)
    ):
        _log(f"gunner: enemy {bld_name} at ({at.x},{at.y}), need to clear")
        if pos == at:
            _log(f"gunner: enemy {bld_name} at ({at.x},{at.y}), firing")
            return Direction.CENTRE, Fire()
        if builder_dist <= 2:
            d = pos.direction_to(at)
            if ct.can_move(d):
                _log(f"gunner: adjacent to enemy, moving {d.name} onto ({at.x},{at.y})")
                return d, None
            _log(f"gunner: adjacent but can't move {d.name}")
        _log(
            f"gunner: walking toward enemy {bld_name} at ({at.x},{at.y}) d²={builder_dist}"
        )
        return _move_or_none(state, ct, at)

    if pos == at:
        _log(f"gunner: on target tile ({at.x},{at.y}), stepping off to build")
        return step_off_and_build(ct, PlaceGunner(at, facing))
    if builder_dist <= 2:
        if bld is not None and bld.team == state.my_team and ct.can_destroy(at):
            _log(
                f"gunner: destroying allied {bld_name} at ({at.x},{at.y}) to place gunner"
            )
            ct.destroy(at)
        can = ct.can_build_gunner(at, facing)
        _log(
            f"gunner: placing at ({at.x},{at.y}) facing {facing.name}, can_build={can}"
        )
        if can:
            return Direction.CENTRE, PlaceGunner(at, facing)
        _log(f"gunner: can_build_gunner returned False at ({at.x},{at.y})")
    _log(f"gunner: walking toward ({at.x},{at.y}) d²={builder_dist}")
    return _move_or_none(state, ct, at)


def _find_siege_tile(
    state: State,
    from_x: int,
    from_y: int,
    en_core: Position,
) -> tuple[int, int] | None:
    """Closest tile to (from_x, from_y) that can actually hit core via LoS ray."""
    w, h = state.w, state.h
    env = state.env
    building = state.building
    ct = _make_core_tiles(state, en_core)
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
            # Quick distance filter before expensive LoS check
            dist = (from_x - cx) ** 2 + (from_y - cy) ** 2
            if dist >= best_dist:
                continue
            if _can_hit_core_fast(w, h, env, building, ct, cx, cy) is not None:
                best_dist = dist
                best = (cx, cy)

    return best


def _find_rush_ore(
    state: State,
    en_core: Position,
) -> tuple[str, int, int, int] | None:
    """Find best ore near enemy core."""
    w = state.w
    f = state.flow
    best: tuple[str, int, int, int] | None = None
    best_dist = INF

    all_ore: set[int] = set(state.ore_ti)
    # Mirror ore using symmetry — confirmed or all remaining candidates
    syms: list[Symmetry] = (
        [state.symmetry] if state.symmetry is not None else list(state.sym_candidates)
    )
    for sym in syms:
        for oi in list(state.ore_ti):
            ox, oy = oi % w, oi // w
            match sym:
                case Symmetry.ROT:
                    mx, my = w - 1 - ox, state.h - 1 - oy
                case Symmetry.HOR:
                    mx, my = ox, state.h - 1 - oy
                case Symmetry.VER:
                    mx, my = w - 1 - ox, oy
            if 0 <= mx < w and 0 <= my < state.h:
                mi = my * w + mx
                # Only add if we haven't seen that tile yet (could be wrong guess)
                if state.env[mi] is None:
                    all_ore.add(mi)

    _log(
        f"_find_rush_ore: {len(all_ore)} total ore, {len(state.ore_ti)} seen, sym={state.symmetry} candidates={state.sym_candidates}"
    )
    for oi in all_ore:
        ox, oy = oi % w, oi // w
        if not _on_enemy_half(state, ox, oy):
            continue
        ore_p = Position(ox, oy)
        if oi in state.blocked_ore:
            rnd = state.age + state.birthday
            blocked_at = state.blocked_ore[oi]
            # TTL: unblock after 100 rounds
            if rnd - blocked_at > 100:
                state.blocked_ore.pop(oi, None)
            # Unblock if we can see it now and it's free
            elif state.last_seen[oi] == rnd:
                bld_check = state.building[oi]
                if bld_check is None and ore_p not in state.unit_tiles:
                    state.blocked_ore.pop(oi, None)
                else:
                    continue
            else:
                continue
        # Skip if enemy unit standing on the ore
        if ore_p in state.unit_tiles:
            state.blocked_ore[oi] = state.age + state.birthday
            continue
        dist = (ox - en_core.x) ** 2 + (oy - en_core.y) ** 2

        bld = state.building[oi]
        bld_name = type(bld).__name__ if bld else "None"
        _log(f"  ore ({ox},{oy}) d²={dist} bld={bld_name} env={state.env[oi]}")

        if oi in state.my_harvesters:
            # Skip if harvester's flow is already committed to gunners
            available = 0.25 - f.gunners_fed[oi]
            if available < 0.1:
                continue
            tap = _find_free_adjacent(state, ox, oy)
            if tap is not None and dist < best_dist:
                best_dist = dist
                best = ("ours", oi, tap[0], tap[1])
            continue

        # Skip ore with non-removable buildings (barriers, conveyors, etc.)
        if bld is not None and not isinstance(
            bld, (BuildingRoad, BuildingMarker, BuildingHarvester)
        ):
            state.blocked_ore[oi] = state.age + state.birthday
            continue

        # Enemy harvester — parasitize (slight preference, free flow)
        if oi in state.en_harvesters:
            tap = _find_free_adjacent(state, ox, oy)
            if tap is not None and dist - 10 < best_dist:
                best_dist = dist - 10
                best = ("parasite", oi, tap[0], tap[1])
            continue

        if not isinstance(bld, BuildingHarvester):
            env = state.env[oi]
            if env is None:
                pass  # mirrored from symmetry
            elif env != Environment.ORE_TITANIUM:
                continue
            tap = _find_free_adjacent(state, ox, oy)
            if tap is not None and dist < best_dist:
                best_dist = dist
                best = ("free", oi, tap[0], tap[1])
            continue

    if best is not None:
        _log(f"  PICKED: {best[0]} ore at ({best[2]},{best[3]}) d²={best_dist}")
    else:
        _log("  PICKED: None")
    return best


def _find_free_adjacent(
    state: State,
    ox: int,
    oy: int,
) -> tuple[int, int] | None:
    w = state.w
    for dx, dy in DIR4_DELTA:
        nx, ny = ox + dx, oy + dy
        if not state.in_bounds(nx, ny):
            continue
        env = state.env[ny * w + nx]
        if env in (
            Environment.WALL,
            Environment.ORE_TITANIUM,
            Environment.ORE_AXIONITE,
        ):
            continue
        ni = ny * w + nx
        bld = state.building[ni]
        match bld:
            case None | BuildingRoad() | BuildingMarker():
                return (nx, ny)
    return None
