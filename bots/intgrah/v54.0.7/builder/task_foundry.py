from __future__ import annotations

from typing import TYPE_CHECKING, Final

from building import (
    BuildingArmouredConveyor,
    BuildingConveyor,
    BuildingFoundry,
    BuildingSplitter,
)
from cambc import Direction, EntityType, Environment, Position, ResourceType
from util import DIR4, can_afford

from .helpers import make_move, try_place

if TYPE_CHECKING:
    from cambc import Controller

    from .state import State

MIN_ROUND: Final[int] = 500


def _core_adj_tiles(state: State) -> list[Position]:
    cx, cy = state.my_core.x, state.my_core.y
    seen: set[tuple[int, int]] = set()
    result: list[Position] = []
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            core_tile = Position(cx + dx, cy + dy)
            for d in DIR4:
                adj = core_tile.add(d)
                if not state.in_bounds(adj):
                    continue
                key = (adj.x, adj.y)
                if key in seen:
                    continue
                seen.add(key)
                if adj.distance_squared(state.my_core) > 2:
                    result.append(adj)
    return result


def _detect_input_direction(state: State, pos: Position) -> Direction | None:
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


def _has_splitter_near_core(state: State, ct: Controller) -> bool:
    for pos in _core_adj_tiles(state):
        bld = state.get_building(pos)
        if isinstance(bld, BuildingSplitter) and bld.team == ct.get_team():
            return True
    return False


def _sees_raw_ax_near_core(state: State, ct: Controller) -> bool:
    for pos in _core_adj_tiles(state):
        if not ct.is_in_vision(pos):
            continue
        bid = ct.get_tile_building_id(pos)
        if bid is None:
            continue
        etype = ct.get_entity_type(bid)
        if etype not in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR):
            continue
        if ct.get_team(bid) != ct.get_team():
            continue
        if ct.get_stored_resource(bid) == ResourceType.RAW_AXIONITE:
            return True
    return False


def _find_conv_for_splitter(
    state: State, ct: Controller
) -> tuple[Position, Position] | None:
    if _has_splitter_near_core(state, ct):
        return None
    for pos in _core_adj_tiles(state):
        bld = state.get_building(pos)
        if not isinstance(bld, (BuildingConveyor, BuildingArmouredConveyor)):
            continue
        if bld.team != ct.get_team():
            continue
        for d in DIR4:
            fnd_pos = pos.add(d)
            if not state.in_bounds(fnd_pos):
                continue
            if fnd_pos.distance_squared(state.my_core) <= 2:
                continue
            if fnd_pos.distance_squared(state.my_core) > 8:
                continue
            if state.get_building(fnd_pos) is not None:
                continue
            if state.get_env(fnd_pos) == Environment.WALL:
                continue
            return pos, fnd_pos
    return None


def _find_foundry_site(state: State, ct: Controller) -> Position | None:
    for pos in _core_adj_tiles(state):
        bld = state.get_building(pos)
        if not isinstance(bld, BuildingSplitter):
            continue
        if bld.team != ct.get_team():
            continue
        for d in DIR4:
            fnd_pos = pos.add(d)
            if not state.in_bounds(fnd_pos):
                continue
            if fnd_pos.distance_squared(state.my_core) <= 2:
                continue
            if fnd_pos.distance_squared(state.my_core) > 8:
                continue
            bld_at = state.get_building(fnd_pos)
            if isinstance(bld_at, BuildingFoundry):
                return None
            if bld_at is not None:
                continue
            if state.get_env(fnd_pos) == Environment.WALL:
                continue
            return fnd_pos
    return None


def task_place_splitter(state: State, ct: Controller) -> bool:
    if ct.get_current_round() < MIN_ROUND:
        return False
    has_ax = any(e == Environment.ORE_AXIONITE for e in state.env)
    if not has_ax:
        return False
    pair = _find_conv_for_splitter(state, ct)
    if ct.get_current_round() % 50 == 0:
        n_adj = len(_core_adj_tiles(state))
        n_conv = sum(
            1
            for p in _core_adj_tiles(state)
            if isinstance(
                state.get_building(p), (BuildingConveyor, BuildingArmouredConveyor)
            )
            and state.get_building(p).team == ct.get_team()
        )
        print(
            f"    splitter: has_ax={has_ax} has_splitter={_has_splitter_near_core(state, ct)} adj={n_adj} conv={n_conv} pair={pair is not None}"
        )
    if pair is None:
        return False
    conv_pos, _fnd_pos = pair
    if ct.get_position().distance_squared(conv_pos) > 2:
        make_move(state, ct, conv_pos)
        return True
    bld = state.get_building(conv_pos)
    if not isinstance(bld, (BuildingConveyor, BuildingArmouredConveyor)):
        return False
    input_dir = _detect_input_direction(state, conv_pos)
    if input_dir is None:
        return False
    if ct.can_destroy(conv_pos):
        ct.destroy(conv_pos)
    if ct.can_build(EntityType.SPLITTER, conv_pos, input_dir):
        ct.build(EntityType.SPLITTER, conv_pos, input_dir)
    return True


def task_place_foundry(state: State, ct: Controller) -> bool:
    rnd = ct.get_current_round()
    if rnd < MIN_ROUND:
        return False
    if rnd - state.last_foundry_round < 20:
        return False
    if _has_foundry(state, ct):
        return False
    if not can_afford(ct, EntityType.FOUNDRY):
        return False
    pos = _find_foundry_site(state, ct)
    if pos is None:
        return False
    if ct.get_position().distance_squared(pos) > 2:
        make_move(state, ct, pos)
        return True
    if try_place(ct, EntityType.FOUNDRY, pos):
        state.last_foundry_round = ct.get_current_round()
    return True
