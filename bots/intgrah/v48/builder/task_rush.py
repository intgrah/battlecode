from building import (
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingHarvester,
    BuildingLauncher,
    BuildingSplitter,
)
from cambc import Controller, Direction, Environment, GameConstants, Position

from .build import Action, Fire, PlaceLauncher, PlaceSentinel
from .helpers import move_toward_with_road
from .state import COST_IMPASSABLE, State
from .state_helpers import mirror


def rush(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    pos = state.pos

    gunner_spot = _find_sentinel_spot(state)
    if gunner_spot is not None:
        tile, direction = gunner_spot
        state.debug_target = (tile, 0, 255, 0)
        if pos == tile:
            adj = _step_off(state, pos)
            if adj is not None:
                return move_toward_with_road(state, ct, adj)
            return Direction.CENTRE, None
        if pos.distance_squared(tile) <= GameConstants.ACTION_RADIUS_SQ:
            return Direction.CENTRE, PlaceSentinel(tile, direction)
        return _nav_to(state, ct, tile)

    key_target = _find_key_target(state)
    if key_target is not None:
        state.debug_target = (key_target, 255, 255, 0)
        if pos == key_target:
            ti, _ = ct.get_global_resources()
            atk_ti, _ = GameConstants.BUILDER_BOT_ATTACK_COST
            if ti >= atk_ti and ct.can_fire(pos):
                return Direction.CENTRE, Fire(pos)
            return Direction.CENTRE, None

        launcher = _find_friendly_launcher_for(state, key_target)
        if launcher is not None:
            state.debug_target = (launcher, 0, 255, 255)
            if pos.distance_squared(launcher) <= 1:
                return Direction.CENTRE, None
            return _nav_to(state, ct, launcher)

        launcher_site = _find_launcher_site(state, key_target)
        if launcher_site is not None:
            state.debug_target = (launcher_site, 255, 0, 255)
            if pos == launcher_site:
                adj = _step_off(state, pos)
                if adj is not None:
                    return move_toward_with_road(state, ct, adj)
                return Direction.CENTRE, None
            if pos.distance_squared(launcher_site) <= GameConstants.ACTION_RADIUS_SQ:
                return Direction.CENTRE, PlaceLauncher(launcher_site)
            return _nav_to(state, ct, launcher_site)

    target = _rush_target(state)
    if target is None:
        return None
    move, build = move_toward_with_road(state, ct, target)
    if move == Direction.CENTRE and build is None:
        return None
    state.debug_target = (target, 255, 0, 0)
    return move, build


def _en_core_center(state: State) -> Position | None:
    if not state.en_core_tiles:
        return None
    sx = sum(p.x for p in state.en_core_tiles)
    sy = sum(p.y for p in state.en_core_tiles)
    n = len(state.en_core_tiles)
    return Position(sx // n, sy // n)


def _output_tiles(state: State, p: Position) -> list[Position]:
    i = state.idx(p.x, p.y)
    bld = state.building[i]
    results: list[Position] = []
    match bld:
        case BuildingHarvester():
            for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                nx, ny = p.x + dx, p.y + dy
                if state.in_bounds(nx, ny):
                    results.append(Position(nx, ny))
        case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
            dx, dy = d.delta()
            nx, ny = p.x + dx, p.y + dy
            if state.in_bounds(nx, ny):
                results.append(Position(nx, ny))
        case BuildingSplitter(direction=d):
            dx, dy = d.delta()
            for odx, ody in ((dx, dy), (-dy, dx), (dy, -dx)):
                nx, ny = p.x + odx, p.y + ody
                if state.in_bounds(nx, ny):
                    results.append(Position(nx, ny))
        case BuildingBridge(target=t):
            if state.in_bounds(t.x, t.y):
                results.append(t)
    return results


def _has_flow(state: State, p: Position) -> bool:
    i = state.idx(p.x, p.y)
    if state.en_flow.total[i] > 0:
        return True
    match state.building[i]:
        case BuildingHarvester():
            return True
    return False


def _find_sentinel_spot(state: State) -> tuple[Position, Direction] | None:
    core = _en_core_center(state)
    if core is None:
        return None
    sources = state.en_harvesters | state.en_transport
    for p in sources:
        if not _has_flow(state, p):
            continue
        for candidate in _output_tiles(state, p):
            if not _in_sentinel_range_of_core(state, candidate):
                continue
            ni = state.idx(candidate.x, candidate.y)
            if state.building[ni] is not None:
                continue
            env = state.env[ni]
            if env is None or env == Environment.WALL:
                continue
            d = candidate.direction_to(core)
            if d == Direction.CENTRE:
                continue
            return candidate, d
    return None


def _in_sentinel_range_of_core(state: State, p: Position) -> bool:
    return any(
        p.distance_squared(ct) <= GameConstants.SENTINEL_VISION_RADIUS_SQ
        for ct in state.en_core_tiles
    )


def _find_key_target(state: State) -> Position | None:
    if not state.en_core_tiles:
        return None
    f = state.en_flow
    best: Position | None = None
    best_flow = 0.0
    for p in state.en_transport | state.en_harvesters:
        i = state.idx(p.x, p.y)
        if f.total[i] <= 0 and p not in state.en_harvesters:
            continue
        if not _in_sentinel_range_of_core(state, p):
            continue
        flow = f.total[i] if p not in state.en_harvesters else max(f.total[i], 0.25)
        if flow > best_flow:
            best_flow = flow
            best = p
    return best


def _find_friendly_launcher_for(state: State, target: Position) -> Position | None:
    for p in state.my_turrets:
        i = state.idx(p.x, p.y)
        bld = state.building[i]
        if (
            isinstance(bld, BuildingLauncher)
            and bld.team == state.my_team
            and p.distance_squared(target) <= GameConstants.LAUNCHER_VISION_RADIUS_SQ
        ):
            return p
    return None


def _find_launcher_site(state: State, target: Position) -> Position | None:
    best: Position | None = None
    best_dist = 999999
    pos = state.pos
    r = 5
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            nx, ny = target.x + dx, target.y + dy
            if not state.in_bounds(nx, ny):
                continue
            candidate = Position(nx, ny)
            if (
                candidate.distance_squared(target)
                > GameConstants.LAUNCHER_VISION_RADIUS_SQ
            ):
                continue
            ni = state.idx(nx, ny)
            env = state.env[ni]
            if env is None or env != Environment.EMPTY:
                continue
            if state.building[ni] is not None:
                continue
            if state.walkable(nx, ny) >= COST_IMPASSABLE:
                continue
            d = pos.distance_squared(candidate)
            if d < best_dist:
                best_dist = d
                best = candidate
    return best


def _step_off(state: State, pos: Position) -> Position | None:
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            if dx == 0 and dy == 0:
                continue
            nx, ny = pos.x + dx, pos.y + dy
            if not state.in_bounds(nx, ny):
                continue
            if state.walkable(nx, ny) < COST_IMPASSABLE:
                return Position(nx, ny)
    return None


def _nav_to(
    state: State,
    ct: Controller,
    target: Position,
) -> tuple[Direction, Action | None] | None:
    move, build = move_toward_with_road(state, ct, target)
    if move == Direction.CENTRE and build is None:
        return None
    return move, build


def _rush_target(state: State) -> Position | None:
    if state.en_core_tiles:
        return min(state.en_core_tiles, key=lambda p: p.distance_squared(state.pos))
    if state.symmetry is not None:
        return mirror(state, state.my_core)
    w, h = state.w, state.h
    cx, cy = state.my_core.x, state.my_core.y
    return Position(w - 1 - cx, h - 1 - cy)
