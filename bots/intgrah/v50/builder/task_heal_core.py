"""Heal the core."""

from action import ActionOnly, Heal, Turn
from cambc import Controller, GameConstants, Position

from .helpers import move_toward_with_road
from .state import State


def heal_core(
    state: State,
    ct: Controller,
) -> Turn | None:
    if state.my_core_hp >= GameConstants.CORE_MAX_HP:
        return None

    core = Position(state.my_core[0], state.my_core[1])

    if ct.can_heal(core):
        print(f"    heal_core: hp={state.my_core_hp}")
        return ActionOnly(Heal(core))

    cx, cy = state.my_core
    w = state.w
    nav_dist = state.nav_dist
    best: Position | None = None
    best_d = -1
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            ax, ay = cx + dx, cy + dy
            if not state.in_bounds(ax, ay):
                continue
            d = nav_dist[ay * w + ax]
            if d != -1 and (best is None or d < best_d):
                best_d = d
                best = Position(ax, ay)

    if best is None:
        return None
    result = move_toward_with_road(state, ct, best)
    if result is None:
        return None
    print(f"    heal_core: nav to ({best.x},{best.y}) hp={state.my_core_hp}")
    ct.draw_indicator_line(state.pos, best, 255, 0, 0)
    return result
