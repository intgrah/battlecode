from cambc import Controller, Direction, Position
from util import INF

from .action import Action, Fire
from .helpers import move_toward_with_road
from .state import State


def _find_target(state: State) -> Position | None:
    pos = state.pos
    best: Position | None = None
    best_dist = INF
    w = state.w
    for idx in state.en_transport:
        tx, ty = idx % w, idx // w
        dist = abs(pos.x - tx) + abs(pos.y - ty)
        if dist < best_dist:
            best_dist = dist
            best = Position(tx, ty)
    return best


def fire_enemy_transport(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    fire_pos = _find_target(state)
    if fire_pos is None:
        return None
    pos = state.pos

    if pos == fire_pos:
        return Direction.CENTRE, Fire()

    move, build = move_toward_with_road(state, ct, fire_pos)
    if move != Direction.CENTRE and build is None:
        new_pos = pos.add(move)
        if new_pos == fire_pos:
            build = Fire()
    ct.draw_indicator_line(state.pos, fire_pos, 255, 128, 0)
    return move, build
