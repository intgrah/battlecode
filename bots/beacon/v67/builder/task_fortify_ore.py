"""Fortify ore: build a harvester on titanium ore, then place 2 sentinels
on the cardinal sides facing toward the enemy, and barriers on the other 2.
Waits for resources if needed.
"""

from cambc import Controller, Direction, EntityType, Environment, Position
from marker import TaskClaim, TaskKind
from util import DIR4_DELTA, DIR8_DELTA

from .build import Action, PlaceBarrier, PlaceHarvester, PlaceSentinel
from .helpers import is_claimed, move_toward_with_road
from .state import COST_IMPASSABLE, State

# Map (dx, dy) from ore to sentinel position -> outward facing direction
_OUTWARD_DIR: dict[tuple[int, int], Direction] = {
    (0, -1): Direction.NORTH,
    (0, 1): Direction.SOUTH,
    (1, 0): Direction.EAST,
    (-1, 0): Direction.WEST,
}


def _sentinel_dirs(state: State, ox: int, oy: int) -> set[tuple[int, int]]:
    """Pick 2 cardinal directions for sentinels — the 2 facing most toward
    the enemy core (or map center if enemy core unknown). Deterministic
    per ore tile.
    """
    if state.en_core is not None:
        tx, ty = state.en_core
    else:
        tx, ty = state.w // 2, state.h // 2

    # Score each cardinal direction by how much it points toward the target
    scored: list[tuple[float, tuple[int, int]]] = []
    for dx, dy in DIR4_DELTA:
        ax, ay = ox + dx, oy + dy
        if not state.in_bounds(ax, ay):
            continue
        env = state.env[state.idx(ax, ay)]
        if env in (
            Environment.WALL,
            Environment.ORE_TITANIUM,
            Environment.ORE_AXIONITE,
        ):
            continue
        # Lower distance to target = more toward enemy = higher priority
        dist = abs(ax - tx) + abs(ay - ty)
        scored.append((dist, (dx, dy)))
    scored.sort(key=lambda t: t[0])
    return {d for _, d in scored[:2]}


def _needs_work(state: State, ox: int, oy: int) -> tuple[int, int, bool] | None:
    """Return the first cardinal neighbor that needs a sentinel or barrier.

    Returns (ax, ay, is_sentinel) or None if fully fortified.
    """
    done = frozenset({EntityType.SENTINEL, EntityType.BARRIER})
    sent_dirs = _sentinel_dirs(state, ox, oy)
    for dx, dy in DIR4_DELTA:
        ax, ay = ox + dx, oy + dy
        if not state.in_bounds(ax, ay):
            continue
        env = state.env[state.idx(ax, ay)]
        if env in (
            Environment.WALL,
            Environment.ORE_TITANIUM,
            Environment.ORE_AXIONITE,
        ):
            continue
        ent = state.entity[state.idx(ax, ay)]
        # Skip if any friendly defensive building already here
        if ent is not None and ent[0] in done and ent[1] == state.my_team:
            continue
        is_sentinel_spot = (dx, dy) in sent_dirs
        return (ax, ay, is_sentinel_spot)
    return None


def _best_ore(state: State) -> tuple[int, int] | None:
    """Pick visible Ti ore closest to the bot that needs fortification."""
    pos = state.pos
    best: tuple[int, int] | None = None
    best_dist = 999999

    for ox, oy in state.ore_ti - state.my_harvested - state.en_harvested:
        oi = state.idx(ox, oy)
        if state.last_seen[oi] == 0:
            continue
        if is_claimed(state, oi, TaskKind.NAV_ORE):
            continue
        dist = abs(pos.x - ox) + abs(pos.y - oy)
        if dist < best_dist:
            best_dist = dist
            best = (ox, oy)

    done: list[int] = []
    for oi in state.my_fortify_targets:
        ox, oy = oi % state.w, oi // state.w
        if _needs_work(state, ox, oy) is None:
            done.append(oi)
            continue
        dist = abs(pos.x - ox) + abs(pos.y - oy)
        if dist < best_dist:
            best_dist = dist
            best = (ox, oy)
    # Permanently stop tracking completed outposts
    for oi in done:
        state.my_fortify_targets.discard(oi)

    return best


def _reachable_adjacent(
    state: State,
    pos: Position,
    tx: int,
    ty: int,
) -> Position | None:

    best: Position | None = None
    best_dist = 999999
    for dx, dy in DIR8_DELTA:
        ax, ay = tx + dx, ty + dy
        if not state.in_bounds(ax, ay):
            continue
        if state.walkable(ax, ay) >= COST_IMPASSABLE:
            continue
        dist = (pos.x - ax) ** 2 + (pos.y - ay) ** 2
        if dist < best_dist:
            best_dist = dist
            best = Position(ax, ay)
    return best


def fortify_ore(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    ore = _best_ore(state)
    if ore is None:
        return None
    ox, oy = ore
    oi = state.idx(ox, oy)
    ore_pos = Position(ox, oy)

    rnd = ct.get_current_round()
    state.claim = TaskClaim(TaskKind.NAV_ORE, oi, rnd)

    # Step 1: if ore has no harvester yet, build one
    ore_ent = state.entity[oi]
    ore_has_harvester = (
        ore_ent is not None
        and ore_ent[0] == EntityType.HARVESTER
        and ore_ent[1] == state.my_team
    )

    if not ore_has_harvester:
        if state.pos.distance_squared(ore_pos) <= 2:
            bid = ct.get_tile_building_id(ore_pos)
            if bid is not None and ct.can_destroy(ore_pos):
                ct.destroy(ore_pos)
            h_cost, _ = ct.get_harvester_cost()
            ti, _ = ct.get_global_resources()
            if ti >= h_cost and ct.can_build_harvester(ore_pos):
                state.my_fortify_targets.add(oi)
                return Direction.CENTRE, PlaceHarvester(ore_pos)
            return Direction.CENTRE, None

        adj = _reachable_adjacent(state, state.pos, ox, oy)
        if adj is None:
            return None
        move, build = move_toward_with_road(state, ct, adj)
        if move != Direction.CENTRE and build is None:
            new_pos = state.pos.add(move)
            if new_pos.distance_squared(ore_pos) <= 2:
                h_cost, _ = ct.get_harvester_cost()
                ti, _ = ct.get_global_resources()
                if ti >= h_cost:
                    state.my_fortify_targets.add(oi)
                    build = PlaceHarvester(ore_pos)
        state.debug_target = (ore_pos, 0, 255, 0)
        return move, build

    # Step 2: place sentinels (2) and barriers (2) on cardinal neighbors
    work = _needs_work(state, ox, oy)
    if work is None:
        return None
    sx, sy, is_sentinel = work
    spot_pos = Position(sx, sy)
    dx, dy = sx - ox, sy - oy
    facing = _OUTWARD_DIR.get((dx, dy), Direction.NORTH)

    if is_sentinel:
        action: Action = PlaceSentinel(spot_pos, facing)
        cost, _ = ct.get_sentinel_cost()
    else:
        action = PlaceBarrier(spot_pos)
        cost, _ = ct.get_barrier_cost()

    if state.pos.distance_squared(spot_pos) <= 2 and state.pos != spot_pos:
        ti, _ = ct.get_global_resources()
        if ti >= cost:
            return Direction.CENTRE, action
        return Direction.CENTRE, None

    adj = _reachable_adjacent(state, state.pos, sx, sy)
    if adj is None:
        return None
    move, build = move_toward_with_road(state, ct, adj)
    if move != Direction.CENTRE and build is None:
        new_pos = state.pos.add(move)
        if new_pos.distance_squared(spot_pos) <= 2 and new_pos != spot_pos:
            build = action
    state.debug_target = (spot_pos, 255, 128, 0)
    return move, build
