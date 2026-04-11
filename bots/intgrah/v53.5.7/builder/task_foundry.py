from __future__ import annotations

from typing import TYPE_CHECKING, Final

from building import (
    BuildingArmouredConveyor,
    BuildingConveyor,
    BuildingFoundry,
    BuildingSplitter,
)
from cambc import Direction, EntityType, Environment, Position
from util import DIR4, can_afford

from builder.helpers import make_move, try_place

if TYPE_CHECKING:
    from cambc import Controller

    from builder.state import State

MIN_ROUND: Final[int] = 500


def _has_mixed_flow(fh: int) -> bool:
    has_ti = False
    has_ax = False
    for s in range(0, 16, 2):
        code = (fh >> s) & 0b11
        if code == 1:
            has_ti = True
        elif code == 2:
            has_ax = True
    return has_ti and has_ax


def _count_inputs(state: State, pos: Position) -> int:
    count = 0
    for d in DIR4:
        neighbor = pos.add(d)
        nb = state.get_building(neighbor)
        if isinstance(nb, (BuildingConveyor, BuildingArmouredConveyor)):
            if nb.direction == d.opposite():
                count += 1
        elif isinstance(nb, BuildingSplitter) and nb.direction != d:
            count += 1
    return count


def _input_direction(state: State, pos: Position) -> Direction | None:
    for d in DIR4:
        neighbor = pos.add(d)
        nb = state.get_building(neighbor)
        if isinstance(nb, (BuildingConveyor, BuildingArmouredConveyor)):
            if nb.direction == d.opposite():
                return d.opposite()
        elif isinstance(nb, BuildingSplitter) and nb.direction != d:
            return d.opposite()
    return None


def _has_foundry(state: State, ct: Controller) -> bool:
    for bld in state.buildings:
        if isinstance(bld, BuildingFoundry) and bld.team == ct.get_team():
            return True
    return False


def _find_empty_adj(state: State, pos: Position) -> Position | None:
    for d in DIR4:
        fnd = pos.add(d)
        if not state.in_bounds(fnd):
            continue
        if state.get_env(fnd) == Environment.WALL:
            continue
        if state.get_building(fnd) is not None:
            continue
        return fnd
    return None


def _find_splitter_target(state: State, ct: Controller) -> Position | None:
    if _has_foundry(state, ct):
        return None
    w = state.w
    best: Position | None = None
    best_dist = float("inf")
    my_pos = ct.get_position()
    for pos in ct.get_nearby_tiles():
        i = pos.y * w + pos.x
        bld = state.buildings[i]
        if not isinstance(bld, (BuildingConveyor, BuildingArmouredConveyor)):
            continue
        if bld.team != ct.get_team():
            continue
        if not _has_mixed_flow(state.flow_history[i]):
            continue
        if _count_inputs(state, pos) != 1:
            continue
        if _find_empty_adj(state, pos) is None:
            continue
        dist = my_pos.distance_squared(pos)
        if dist < best_dist:
            best_dist = dist
            best = pos
    return best


def task_place_splitter(state: State, ct: Controller) -> bool:
    if ct.get_current_round() < MIN_ROUND:
        return False
    conv_pos = _find_splitter_target(state, ct)
    if conv_pos is None:
        return False
    if ct.get_position().distance_squared(conv_pos) > 2:
        make_move(state, ct, conv_pos)
        return True
    bld = state.get_building(conv_pos)
    if not isinstance(bld, (BuildingConveyor, BuildingArmouredConveyor)):
        return False
    input_dir = _input_direction(state, conv_pos)
    if input_dir is None:
        return False
    if ct.can_destroy(conv_pos):
        ct.destroy(conv_pos)
    if ct.can_build(EntityType.SPLITTER, conv_pos, input_dir):
        ct.build(EntityType.SPLITTER, conv_pos, input_dir)
    return True


def task_place_foundry(state: State, ct: Controller) -> bool:
    if ct.get_current_round() < MIN_ROUND:
        return False
    if _has_foundry(state, ct):
        return False
    if not can_afford(ct, EntityType.FOUNDRY):
        return False
    w = state.w
    best_splitter: Position | None = None
    best_dist = float("inf")
    my_pos = ct.get_position()
    for pos in ct.get_nearby_tiles():
        i = pos.y * w + pos.x
        bld = state.buildings[i]
        if not isinstance(bld, BuildingSplitter):
            continue
        if bld.team != ct.get_team():
            continue
        if _find_empty_adj(state, pos) is None:
            continue
        dist = my_pos.distance_squared(pos)
        if dist < best_dist:
            best_dist = dist
            best_splitter = pos
    if best_splitter is None:
        return False
    fnd_pos = _find_empty_adj(state, best_splitter)
    if fnd_pos is None:
        return False
    if ct.get_position().distance_squared(fnd_pos) > 2:
        make_move(state, ct, fnd_pos)
        return True
    try_place(ct, EntityType.FOUNDRY, fnd_pos)
    return True
