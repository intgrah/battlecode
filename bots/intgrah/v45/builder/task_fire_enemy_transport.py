from cambc import Controller, Direction, Environment, Position
from util import DIR4_DELTA, TRANSPORT

from .build import Action, Fire
from .helpers import move_toward_with_road
from .state import State


def _find_target(state: State) -> tuple[tuple[int, int], tuple[int, int]] | None:
    w = state.w
    pos = state.pos
    best = None
    best_dist = 999999
    for hi in state.en_harvesters:
        if state.env[hi] != Environment.ORE_TITANIUM:
            continue
        hx, hy = hi % w, hi // w
        for dx, dy in DIR4_DELTA:
            nx, ny = hx + dx, hy + dy
            if not state.in_bounds(nx, ny):
                continue
            ni = state.idx(nx, ny)
            ent = state.entity[ni]
            if ent is None:
                continue
            if ent[1] == state.my_team:
                continue
            if ent[0] not in TRANSPORT:
                continue
            dist = abs(pos.x - nx) + abs(pos.y - ny)
            if dist < best_dist:
                best_dist = dist
                best = ((hx, hy), (nx, ny))
    return best


def fire_enemy_transport(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    target = _find_target(state)
    if target is None:
        return None
    _, (tx, ty) = target
    fire_pos = Position(tx, ty)
    pos = state.pos

    if pos == fire_pos:
        return Direction.CENTRE, Fire(fire_pos)

    move, build = move_toward_with_road(state, ct, fire_pos)
    if move != Direction.CENTRE and build is None:
        new_pos = pos.add(move)
        if new_pos == fire_pos:
            build = Fire(fire_pos)
    state.debug_target = (fire_pos, 255, 128, 0)
    return move, build
