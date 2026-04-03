from action import ActionOnly, Fire, MoveAction, MoveOnly, Turn
from cambc import Controller, Position

from .helpers import move_toward_with_road
from .state import State


def _find_target(state: State) -> Position | None:
    best: Position | None = None
    best_hops = -1
    nav_dist = state.nav_dist
    w = state.w
    for idx in state.en_transport:
        d = nav_dist[idx]
        if d == -1:
            continue
        if best is None or d < best_hops:
            best_hops = d
            best = Position(idx % w, idx // w)
    return best


def fire_enemy_transport(
    state: State,
    ct: Controller,
) -> Turn | None:
    fire_pos = _find_target(state)
    if fire_pos is None:
        return None
    pos = state.pos

    if pos == fire_pos:
        return ActionOnly(Fire())

    result = move_toward_with_road(state, ct, fire_pos)
    if result is None:
        return None
    match result:
        case MoveOnly(move):
            new_pos = pos.add(move)
            if new_pos == fire_pos:
                result = MoveAction(move, Fire())
    print(f"    fire_enemy_transport: target=({fire_pos.x},{fire_pos.y})")
    ct.draw_indicator_line(state.pos, fire_pos, 255, 128, 0)
    return result
