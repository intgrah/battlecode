from cambc import Controller, Direction, EntityType, Environment, Position
from marker import TaskClaim, TaskKind
from util import DIR4_DELTA, DIR8_DELTA

from .build import Action, PlaceBarrier, PlaceHarvester
from .helpers import is_claimed, move_toward_with_road
from .state import COST_IMPASSABLE, State

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
    best = DIR4_DELTA[0]
    best_dist = 999999
    for dx, dy in DIR4_DELTA:
        ax, ay = ox + dx, oy + dy
        if not state.in_bounds(ax, ay):
            continue
        dist = abs(ax - cx) + abs(ay - cy)
        if dist < best_dist:
            best_dist = dist
            best = (dx, dy)
    return best


def _is_ore(state: State, x: int, y: int) -> bool:
    if not state.in_bounds(x, y):
        return False
    env = state.env[state.idx(x, y)]
    return env == Environment.ORE_TITANIUM


def _needs_barrier(state: State, ox: int, oy: int) -> list[tuple[int, int]]:
    open_side = _core_side(state, ox, oy)
    result: list[tuple[int, int]] = []
    for dx, dy in DIR4_DELTA:
        if (dx, dy) == open_side:
            continue
        ax, ay = ox + dx, oy + dy
        if not state.in_bounds(ax, ay):
            continue
        env = state.env[state.idx(ax, ay)]
        if env is None or env == Environment.WALL:
            continue
        if _is_ore(state, ax, ay):
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
    for dx, dy in DIR4_DELTA:
        ax, ay = ox + dx, oy + dy
        if state.in_bounds(ax, ay) and state.env[state.idx(ax, ay)] is None:
            return False
    return True


def _best_ore(state: State) -> tuple[int, int] | None:
    unharvested = state.ore_ti - state.my_harvested - state.en_harvested
    if not unharvested:
        return None
    cx, cy = state.my_core
    best = None
    best_key = (999999,)
    for ox, oy in unharvested:
        if not _ore_is_visible(state, ox, oy):
            continue
        oi = state.idx(ox, oy)
        if oi in state.en_barriers:
            continue
        core_dist = abs(ox - cx) + abs(oy - cy)
        key = (core_dist,)
        if key < best_key:
            best_key = key
            best = (ox, oy)
    return best


def _reachable_adjacent(
    state: State,
    pos: Position,
    ox: int,
    oy: int,
) -> Position | None:
    best = None
    best_dist = 999999
    for dx, dy in DIR8_DELTA:
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


def secure_ore(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    pos = state.pos
    ore = _best_ore(state)
    if ore is None:
        return None
    ox, oy = ore
    oi = state.idx(ox, oy)

    if is_claimed(state, oi, TaskKind.NAV_ORE):
        return None

    rnd = ct.get_current_round()
    state.claim = TaskClaim(TaskKind.NAV_ORE, oi, rnd)

    ore_pos = Position(ox, oy)

    if oi in state.my_barriers:
        if pos.distance_squared(ore_pos) <= 2:
            ct.destroy(ore_pos)
        else:
            adj = _reachable_adjacent(state, pos, ox, oy)
            if adj is None:
                return None
            move, build = move_toward_with_road(state, ct, adj)
            state.debug_target = (ore_pos, 255, 255, 0)
            return move, build

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
