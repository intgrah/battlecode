from cambc import Controller, Direction, EntityType, Environment, Position
from marker import TaskClaim, TaskKind

from .build import Action, PlaceBarrier, PlaceBridge, PlaceHarvester
from .helpers import is_claimed, move_toward_with_road
from .state import COST_IMPASSABLE, State

_CARDINAL = [(-1, 0), (1, 0), (0, -1), (0, 1)]

_SECURED = frozenset(
    {
        EntityType.BARRIER,
        EntityType.GUNNER,
        EntityType.SENTINEL,
        EntityType.BREACH,
        EntityType.LAUNCHER,
        EntityType.HARVESTER,
        EntityType.FOUNDRY,
    },
)


def _core_side(state: State, ox: int, oy: int) -> tuple[int, int]:
    cx, cy = state.my_core
    best = _CARDINAL[0]
    best_dist = 999999
    for dx, dy in _CARDINAL:
        ax, ay = ox + dx, oy + dy
        if not state.in_bounds(ax, ay):
            continue
        dist = abs(ax - cx) + abs(ay - cy)
        if dist < best_dist:
            best_dist = dist
            best = (dx, dy)
    return best


def _needs_barrier(state: State, ox: int, oy: int) -> list[tuple[int, int]]:
    open_side = _core_side(state, ox, oy)
    result: list[tuple[int, int]] = []
    for dx, dy in _CARDINAL:
        if (dx, dy) == open_side:
            continue
        ax, ay = ox + dx, oy + dy
        if not state.in_bounds(ax, ay):
            continue
        env = state.env[state.idx(ax, ay)]
        if env is None or env == Environment.WALL:
            continue
        ent = state.entity[state.idx(ax, ay)]
        if ent is not None and ent[0] in _SECURED and ent[1] == state.my_team:
            continue
        result.append((ax, ay))
    return result


def _ore_is_visible(state: State, ox: int, oy: int) -> bool:
    oi = state.idx(ox, oy)
    if state.env[oi] is None:
        return False
    for dx, dy in _CARDINAL:
        ax, ay = ox + dx, oy + dy
        if state.in_bounds(ax, ay) and state.env[state.idx(ax, ay)] is None:
            return False
    return True


def _best_ore(state: State, pos: Position) -> tuple[int, int] | None:
    unharvested = state.ore_ti - state.my_harvested - state.en_harvested
    if not unharvested:
        return None
    cx, cy = state.my_core
    best = None
    best_key = (999999, 999999)
    for ox, oy in unharvested:
        if not _ore_is_visible(state, ox, oy):
            continue
        core_dist = abs(ox - cx) + abs(oy - cy)
        key = (core_dist, abs(ox - pos.x) + abs(oy - pos.y))
        if key < best_key:
            best_key = key
            best = (ox, oy)
    return best


_ACTION_DELTAS = [
    (-1, 0),
    (1, 0),
    (0, -1),
    (0, 1),
    (-1, -1),
    (-1, 1),
    (1, -1),
    (1, 1),
]


def _reachable_adjacent(
    state: State,
    pos: Position,
    ox: int,
    oy: int,
) -> Position | None:
    best = None
    best_dist = 999999
    for dx, dy in _ACTION_DELTAS:
        ax, ay = ox + dx, oy + dy
        if not state.in_bounds(ax, ay):
            continue
        if state.walkable(ax, ay) >= COST_IMPASSABLE:
            continue
        dist = (pos.x - ax) ** 2 + (pos.y - ay) ** 2
        if dist < best_dist:
            best_dist = dist
            best = Position(ax, ay)
    return best


def _bridge_target_toward_core(
    state: State,
    bx: int,
    by: int,
) -> Position | None:
    cx, cy = state.my_core
    best = None
    best_dist = 999999
    for dx in range(-3, 4):
        for dy in range(-3, 4):
            d2 = dx * dx + dy * dy
            if d2 == 0 or d2 > 9:
                continue
            tx, ty = bx + dx, by + dy
            if not state.in_bounds(tx, ty):
                continue
            ti = state.idx(tx, ty)
            if ti in state.my_core_tiles:
                return Position(tx, ty)
            ent = state.entity[ti]
            if ent is not None:
                if ent[0] == EntityType.BRIDGE and ent[1] == state.my_team:
                    dist = abs(tx - cx) + abs(ty - cy)
                    if dist < best_dist:
                        best_dist = dist
                        best = Position(tx, ty)
                    continue
                if ent[0] not in (EntityType.ROAD, EntityType.MARKER):
                    continue
            env = state.env[ti]
            if env is not None and env != Environment.EMPTY:
                continue
            dist = abs(tx - cx) + abs(ty - cy)
            if dist < best_dist:
                best_dist = dist
                best = Position(tx, ty)
    return best


def secure_ore(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    pos = state.pos
    ore = _best_ore(state, pos)
    if ore is None:
        return None
    ox, oy = ore
    oi = state.idx(ox, oy)

    if is_claimed(state, oi, TaskKind.NAV_ORE):
        return None

    rnd = ct.get_current_round()
    state.claim = TaskClaim(TaskKind.NAV_ORE, oi, rnd)

    needs = _needs_barrier(state, ox, oy)

    if needs:
        ax, ay = needs[0]
        barrier_pos = Position(ax, ay)

        if pos.distance_squared(barrier_pos) <= 2 and pos != barrier_pos:
            bid = ct.get_tile_building_id(barrier_pos)
            if bid is not None and ct.can_destroy(barrier_pos):
                ct.destroy(barrier_pos)
            return Direction.CENTRE, PlaceBarrier(barrier_pos)

        target = _reachable_adjacent(state, pos, ax, ay)
        if target is None:
            target = barrier_pos
        move, build = move_toward_with_road(state, ct, target)
        if move != Direction.CENTRE and build is None:
            new_pos = pos.add(move)
            if new_pos.distance_squared(barrier_pos) <= 2 and new_pos != barrier_pos:
                bid = ct.get_tile_building_id(barrier_pos)
                if bid is not None and ct.can_destroy(barrier_pos):
                    ct.destroy(barrier_pos)
                build = PlaceBarrier(barrier_pos)
        state.debug_target = (barrier_pos, 0, 255, 255)
        return move, build

    ore_pos = Position(ox, oy)
    open_dx, open_dy = _core_side(state, ox, oy)
    bridge_pos = Position(ox + open_dx, oy + open_dy)

    harvester_exists = (
        state.entity[oi] is not None
        and state.entity[oi][0] == EntityType.HARVESTER
        and state.entity[oi][1] == state.my_team
    )

    if not harvester_exists:
        if pos.distance_squared(ore_pos) <= 2:
            bid = ct.get_tile_building_id(ore_pos)
            if bid is not None and ct.can_destroy(ore_pos):
                ct.destroy(ore_pos)
            h_cost, _ = ct.get_harvester_cost()
            ti, _ = ct.get_global_resources()
            if ti >= h_cost and ct.can_build_harvester(ore_pos):
                return Direction.CENTRE, PlaceHarvester(ore_pos)

        adj = _reachable_adjacent(state, pos, ox, oy)
        if adj is None:
            return None
        move, build = move_toward_with_road(state, ct, adj)
        if move != Direction.CENTRE and build is None:
            new_pos = pos.add(move)
            if new_pos.distance_squared(ore_pos) <= 2:
                bid = ct.get_tile_building_id(ore_pos)
                if bid is not None and ct.can_destroy(ore_pos):
                    ct.destroy(ore_pos)
                h_cost, _ = ct.get_harvester_cost()
                ti, _ = ct.get_global_resources()
                if ti >= h_cost:
                    build = PlaceHarvester(ore_pos)
        state.debug_target = (ore_pos, 0, 255, 0)
        return move, build

    bi = state.idx(bridge_pos.x, bridge_pos.y)
    bridge_exists = (
        state.entity[bi] is not None
        and state.entity[bi][0] == EntityType.BRIDGE
        and state.entity[bi][1] == state.my_team
    )
    if bridge_exists:
        return None

    bridge_target = _bridge_target_toward_core(state, bridge_pos.x, bridge_pos.y)
    if bridge_target is None:
        return None

    if pos.distance_squared(bridge_pos) <= 2 and pos != bridge_pos:
        bid = ct.get_tile_building_id(bridge_pos)
        if bid is not None and ct.can_destroy(bridge_pos):
            ct.destroy(bridge_pos)
        return Direction.CENTRE, PlaceBridge(bridge_pos, bridge_target)

    adj = _reachable_adjacent(state, pos, bridge_pos.x, bridge_pos.y)
    if adj is None:
        return None
    move, build = move_toward_with_road(state, ct, adj)
    if move != Direction.CENTRE and build is None:
        new_pos = pos.add(move)
        if new_pos.distance_squared(bridge_pos) <= 2 and new_pos != bridge_pos:
            bid = ct.get_tile_building_id(bridge_pos)
            if bid is not None and ct.can_destroy(bridge_pos):
                ct.destroy(bridge_pos)
            build = PlaceBridge(bridge_pos, bridge_target)
    state.debug_target = (bridge_pos, 255, 255, 0)
    return move, build
