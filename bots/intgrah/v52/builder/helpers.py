from building import (
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingSplitter,
)
from cambc import Controller, Direction, EntityType, Position
from util import DIR4, DIR8, Symmetry
from util_extra import can_afford, try_move

from .algorithms.fallback_nav import fallback_nav
from .algorithms.pathfind import pathfind_blocked
from .state import State


def find_path(
    state: State, ct: Controller, start: Position, target: Position
) -> list[Position] | None:
    return pathfind_blocked(state, ct, start, target)


def make_move(state: State, ct: Controller, target: Position) -> bool:
    if ct.get_position() == target:
        return True

    path = find_path(state, ct, ct.get_position(), target)
    if path and len(path) > 1:
        next_step = path[1]
        try_move_with_build(state, ct, next_step)
        return True
    next_move = fallback_nav(state, ct, target)
    if next_move:
        try_move_with_build(state, ct, next_move)
        return True
    return False


def try_move_with_road(ct: Controller, target_pos: Position, state: State) -> bool:
    if state.get_cost(target_pos) > 1 and ct.can_build_road(target_pos):
        ct.build_road(target_pos)
    return try_move(ct, target_pos)


def try_move_with_build(state: State, ct: Controller, target_pos: Position) -> bool:
    return try_move_with_road(ct, target_pos, state)


def try_attack(ct: Controller) -> bool:
    position = ct.get_position()
    if ct.can_fire(position):
        ct.fire(position)
        return True
    return False


def try_place(
    ct: Controller,
    etype: EntityType,
    pos: Position,
    extra: Direction | Position | None = None,
    *,
    destroy: bool = True,
) -> bool:
    if not can_afford(ct, etype):
        return False
    if destroy and ct.can_destroy(pos):
        ct.destroy(pos)
    if ct.can_build(etype, pos, extra):
        ct.build(etype, pos, extra)
        return True
    return False


def trace_downstream(
    state: State,
    start_pos: Position,
    target_head: Position | None,
    path: list[Position] | None = None,
) -> list[Position]:
    if path is None:
        path = []
    current_pos = start_pos
    while True:
        path.append(current_pos)
        bld = state.get_building(current_pos)
        match bld:
            case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
                current_pos = current_pos.add(d)
            case BuildingSplitter(direction=d):
                for sd in DIR4:
                    if sd == d.opposite():
                        continue
                    new_pos = current_pos.add(sd)
                    if target_head:
                        new_path = trace_downstream(
                            state, new_pos, target_head, path=path[:]
                        )
                        if new_path and target_head in new_path:
                            return new_path
                    elif state.get_building(new_pos) is None:
                        path.append(new_pos)
                        return path
                current_pos = current_pos.add(d)
            case BuildingBridge(target=t):
                current_pos = t
            case _:
                break
        if current_pos in path:
            break
    return path


def try_heal(
    state: State, ct: Controller, position: Position, *, conserve_ti: bool = True
) -> bool:
    if conserve_ti and state.repair_pos is not None:
        i = state._idx(state.repair_pos)
        if not state.buildings[i] or state.hp[i] > state.max_hp[i] - 4:
            return False
    if ct.can_heal(position):
        ct.heal(position)
        return True
    return False


def get_enemy_core_pos(state: State) -> Position:
    w, h = state.w, state.h
    cp = state.my_core
    candidates = state.symmetry_candidates

    if Symmetry.ROT in candidates:
        return Position(w - 1 - cp.x, h - 1 - cp.y)
    if Symmetry.VER in candidates:
        return Position(w - 1 - cp.x, cp.y)
    if Symmetry.HOR in candidates:
        return Position(cp.x, h - 1 - cp.y)

    return Position(w - 1 - cp.x, h - 1 - cp.y)


def move_random(state: State, ct: Controller) -> bool:
    dir8 = DIR8[:]
    state.rng.shuffle(dir8)
    for direction in dir8:
        if ct.can_move(direction):
            ct.move(direction)
            return True
    return False


def trace_upstream(state: State, position: Position) -> list[Position]:
    path: list[Position] = []
    conveyors = [position]
    while len(conveyors) > 0:
        position = conveyors[0]
        conveyors = state.get_conveyors_to_here(position)
        if position in path:
            break
        path.append(position)
    return path


def is_enemy_building(state: State, ct: Controller, pos: Position) -> bool:
    b = state.get_building(pos)
    return b is not None and b.team != ct.get_team()
