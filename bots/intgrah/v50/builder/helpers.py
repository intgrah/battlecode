import itertools

from cambc import Controller, Position
from constants import COST_IMPASSABLE
from marker import TaskKind
from navigation import find_path
from util import DIR4_DELTA, INF

from .action import ActionMove, MoveOnly, PlaceRoad, Turn
from .state import State


def move_toward_with_road(
    state: State,
    ct: Controller,
    target: Position,
) -> Turn | None:
    pos = state.pos
    if pos == target:
        return None
    t0 = ct.get_cpu_time_elapsed()
    path = find_path(state, target.x, target.y)
    t1 = ct.get_cpu_time_elapsed()
    print(f"  nav={t1 - t0}us")
    if path is None or len(path) < 2:
        return None
    draw_path(ct, state.w, path)
    w = state.w
    nx, ny = path[1] % w, path[1] // w
    nxt = Position(nx, ny)
    d = pos.direction_to(nxt)
    if ct.can_move(d):
        return MoveOnly(d)
    road_cost, _ = ct.get_road_cost()
    ti, _ = ct.get_global_resources()
    if ti >= road_cost and ct.can_build_road(nxt):
        return ActionMove(PlaceRoad(nxt), d)
    return None


def draw_path(
    ct: Controller,
    w: int,
    path: list[int],
    colour: tuple[int, int, int] = (255, 255, 255),
) -> None:
    for u, v in itertools.pairwise(path):
        y0, x0 = divmod(u, w)
        y1, x1 = divmod(v, w)
        ct.draw_indicator_line(Position(x0, y0), Position(x1, y1), *colour)


def cardinal_adjacent(state: State, pos: Position, target: Position) -> Position | None:
    best = None
    best_dist = INF
    for ddx, ddy in DIR4_DELTA:
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
