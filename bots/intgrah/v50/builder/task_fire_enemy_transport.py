from cambc import Controller, Direction, Position
from config import INF

from .action import Action, Fire
from .helpers import move_toward_with_road
from .state import State


def _find_target(state: State) -> Position | None:
    pos = state.pos
    best: Position | None = None
    best_dist = INF
    for tp in state.en_transport:
        dist = abs(pos.x - tp.x) + abs(pos.y - tp.y)
        if dist < best_dist:
            best_dist = dist
            best = tp
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
    state.debug_target = (fire_pos, 255, 128, 0)
    return move, build
