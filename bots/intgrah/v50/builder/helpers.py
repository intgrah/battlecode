from cambc import Controller, Direction, Position
from marker import TaskKind
from nav import find_path
from util import INF

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
    path = find_path(state, target.x, target.y)
    if path is None or len(path) < 2:
        return Direction.CENTRE
    _draw_path(ct, state.w, path)
    w = state.w
    nx, ny = path[1] % w, path[1] // w
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
    path = find_path(state, target.x, target.y)
    if path is None or len(path) < 2:
        return Direction.CENTRE, None
    _draw_path(ct, state.w, path)
    w = state.w
    nx, ny = path[1] % w, path[1] // w
    nxt = Position(nx, ny)
    d = pos.direction_to(nxt)
    if ct.can_move(d):
        return d, None
    road_cost, _ = ct.get_road_cost()
    ti, _ = ct.get_global_resources()
    if ti >= road_cost and ct.can_build_road(nxt):
        return d, PlaceRoad(nxt)
    return Direction.CENTRE, None


def _draw_path(ct: Controller, w: int, path: list[int]) -> None:
    for i in range(len(path) - 1):
        x0, y0 = path[i] % w, path[i] // w
        x1, y1 = path[i + 1] % w, path[i + 1] // w
        ct.draw_indicator_line(Position(x0, y0), Position(x1, y1), 0, 200, 0)


def cardinal_adjacent(state: State, pos: Position, target: Position) -> Position | None:
    best = None
    best_dist = INF
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
