"""Free helper functions for builder tasks.

These operate on State + Controller without any class instances.
"""

from cambc import Controller, Direction, Position
from marker import TaskKind
from nav_astar import NavAstar

from .build import Action, PlaceRoad
from .state import COST_IMPASSABLE, State


def move_toward(
    state: State,
    ct: Controller,
    target: Position,
) -> Direction:
    pos = state.pos
    if pos == target:
        return Direction.CENTRE
    search = NavAstar(state, pos.x, pos.y, target.x, target.y)
    search.set_budget(ct, 5000)
    raw = search.compute()
    if raw is None or len(raw) < 2:
        return Direction.CENTRE
    w = state.w
    nx, ny = raw[1] % w, raw[1] // w
    nxt = Position(nx, ny)
    d = pos.direction_to(nxt)
    if ct.can_move(d):
        return d
    return Direction.CENTRE


def move_toward_with_road(
    state: State,
    ct: Controller,
    target: Position,
) -> tuple[Direction, Action | None]:
    pos = state.pos
    if pos == target:
        return Direction.CENTRE, None

    if state.nav_target_key != target:
        state.nav_target_key = target
        state.nav_path = None
        state.nav_search = None

    if state.nav_path is not None:
        w = state.w
        pi = pos.y * w + pos.x
        if pi in state.nav_path:
            idx = state.nav_path.index(pi)
            if idx + 1 < len(state.nav_path):
                nxt_i = state.nav_path[idx + 1]
                nx, ny = nxt_i % w, nxt_i // w
                nxt = Position(nx, ny)
                d = pos.direction_to(nxt)
                if ct.can_move(d):
                    return d, None
                road_cost, _ = ct.get_road_cost()
                ti, _ = ct.get_global_resources()
                if ti >= road_cost and ct.can_build_road(nxt):
                    return d, PlaceRoad(nxt)
        state.nav_path = None
        state.nav_search = None

    if state.nav_search is None:
        state.nav_search = NavAstar(state, pos.x, pos.y, target.x, target.y)
    state.nav_search.set_budget(ct, 1800)
    raw = state.nav_search.compute()
    if not state.nav_search.exhausted:
        return Direction.CENTRE, None
    if raw is None or len(raw) < 2:
        return Direction.CENTRE, None
    state.nav_path = raw
    state.nav_search = None
    w = state.w
    nx, ny = raw[1] % w, raw[1] // w
    nxt = Position(nx, ny)
    d = pos.direction_to(nxt)
    if ct.can_move(d):
        return d, None
    road_cost, _ = ct.get_road_cost()
    ti, _ = ct.get_global_resources()
    if ti >= road_cost and ct.can_build_road(nxt):
        return d, PlaceRoad(nxt)
    return Direction.CENTRE, None


def cardinal_adjacent(state: State, pos: Position, target: Position) -> Position | None:
    best = None
    best_dist = 999999
    for ddx, ddy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        ax, ay = target.x + ddx, target.y + ddy
        if not state.in_bounds(ax, ay):
            continue
        if state.walkable(ax, ay) >= COST_IMPASSABLE:
            continue
        dist = (pos.x - ax) ** 2 + (pos.y - ay) ** 2
        if dist < best_dist:
            best_dist = dist
            best = Position(ax, ay)
    return best


def is_claimed(state: State, tile_index: int, kind: TaskKind) -> bool:
    for c in state.claims:
        if c.tile_index == tile_index and c.kind == kind:
            if (
                state.last_claim is not None
                and c.tile_index == state.last_claim.tile_index
                and c.kind == state.last_claim.kind
            ):
                continue
            return True
    return False
