import itertools

from action import ActionMove, MoveOnly, PlaceRoad, Turn
from cambc import Controller, Position
from marker import TaskKind

from .state import State


def extract_path(state: State, gx: int, gy: int) -> list[int] | None:
    """
    Assumption: bfs was already computed in the state update.
    """
    w = state.w
    si = state.pos.y * w + state.pos.x
    gi = gy * w + gx
    if si == gi:
        return [si]
    parent = state.nav_parent
    if parent[gi] == -1:
        return None
    path: list[int] = []
    cur = gi
    while cur != si:
        path.append(cur)
        cur = parent[cur]
    path.append(si)
    path.reverse()
    return path


def move_toward_with_road(
    state: State,
    ct: Controller,
    target: Position,
) -> Turn | None:
    pos = state.pos
    if pos == target:
        return None
    path = extract_path(state, target.x, target.y)
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


def nearest_reachable_at(state: State, target: Position) -> Position | None:
    """
    If you want to place a walkable tile like a road/conveyer/bridge/splitter,
    you can be in any of 9 tiles near the spot you want to build.
    Even if you are standing on the tile you want to build, you can still do that.
    """
    w = state.w
    nav_dist = state.nav_dist
    best: Position | None = None
    best_hops = -1
    tx, ty = target.x, target.y
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            ax, ay = tx + dx, ty + dy
            if not state.in_bounds(ax, ay):
                continue
            d = nav_dist[ay * w + ax]
            if d != -1 and (best is None or d < best_hops):
                best_hops = d
                best = Position(ax, ay)
    return best


def nearest_reachable_around(state: State, target: Position) -> Position | None:
    """
    If you want to place an unwalkable building like a barrier or turret, you must be in the 8 tile
    ring surrounding that tile. If you are on that tile, then you must step aside.
    """
    w = state.w
    nav_dist = state.nav_dist
    best: Position | None = None
    best_hops = -1
    tx, ty = target.x, target.y
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            if dx == 0 and dy == 0:
                continue
            ax, ay = tx + dx, ty + dy
            if not state.in_bounds(ax, ay):
                continue
            d = nav_dist[ay * w + ax]
            if d != -1 and (best is None or d < best_hops):
                best_hops = d
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
