from __future__ import annotations

from typing import TYPE_CHECKING

from building import BuildingCore
from cambc import Controller, Environment, Position
from util import INF, ROAD_COST, Symmetry

if TYPE_CHECKING:
    from builder.state import State

_REFLECT_BUDGET = 25


def _mirror(state: State, pos: Position) -> Position:
    match state.symmetry:
        case Symmetry.ROT:
            return Position(state.w - 1 - pos.x, state.h - 1 - pos.y)
        case Symmetry.HOR:
            return Position(pos.x, state.h - 1 - pos.y)
        case Symmetry.VER:
            return Position(state.w - 1 - pos.x, pos.y)
        case None:
            return pos


def _set_enemy_core(state: State) -> None:
    core = _mirror(state, state.my_core)
    w = state.w
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            cx, cy = core.x + dx, core.y + dy
            if 0 <= cx < state.w and 0 <= cy < state.h:
                state.nav_cost[cy * w + cx] = INF


def _eliminate_symmetries(
    state: State, new_tiles: list[tuple[Position, Environment]]
) -> None:
    if not state.symmetry_candidates:
        return

    w, h = state.w, state.h
    invalid: set[Symmetry] = set()

    for sym in state.symmetry_candidates:
        for pos, env in new_tiles:
            match sym:
                case Symmetry.HOR:
                    sx, sy = pos.x, h - 1 - pos.y
                case Symmetry.VER:
                    sx, sy = w - 1 - pos.x, pos.y
                case Symmetry.ROT:
                    sx, sy = w - 1 - pos.x, h - 1 - pos.y

            mirror_env = state.env[sy * w + sx]
            if mirror_env is not None and mirror_env != env:
                invalid.add(sym)
                break

            b1 = state.buildings[pos.y * w + pos.x]
            b2 = state.buildings[sy * w + sx]
            match b1:
                case BuildingCore():
                    is_core1 = True
                case _:
                    is_core1 = False
            match b2:
                case BuildingCore():
                    is_core2 = True
                case _:
                    is_core2 = False
            if is_core1 != is_core2:
                invalid.add(sym)
                break

    state.symmetry_candidates -= invalid

    if state.symmetry is None and len(state.symmetry_candidates) == 1:
        state.symmetry = next(iter(state.symmetry_candidates))


def update_symmetry(state: State, ct: Controller) -> None:
    w = state.w
    new_tiles: list[tuple[Position, Environment]] = []
    for pos in ct.get_nearby_tiles():
        e = state.env[pos.y * w + pos.x]
        if e is not None:
            new_tiles.append((pos, e))

    had_symmetry = state.symmetry is not None
    if not had_symmetry:
        _eliminate_symmetries(state, new_tiles)
    if state.symmetry is None:
        return

    if had_symmetry:
        source = new_tiles
    else:
        _set_enemy_core(state)
        source = [
            (Position(i % w, i // w), e)
            for i, e in enumerate(state.env)
            if e is not None
        ]
    pending = state.reflect_queue
    for t, env in source:
        m = _mirror(state, t)
        mi = m.y * w + m.x
        if state.env[mi] is not None:
            continue
        state.env[mi] = env
        pending.append(mi)

    _drain_reflect_queue(state)


def _drain_reflect_queue(state: State) -> None:
    pending = state.reflect_queue
    if not pending:
        return
    n = min(len(pending), _REFLECT_BUDGET)
    for _ in range(n):
        i = pending.popleft()
        terrain = state.env[i]
        if terrain == Environment.WALL:
            state.nav_cost[i] = INF
            state.conveyor_cost_grid[i] = INF
        elif terrain in (
            Environment.EMPTY,
            Environment.ORE_TITANIUM,
            Environment.ORE_AXIONITE,
        ):
            state.nav_cost[i] = ROAD_COST
            state.conveyor_cost_grid[i] = 1 if terrain == Environment.EMPTY else 50
