from __future__ import annotations

from typing import TYPE_CHECKING, Final

from building import (
    BuildingArmouredConveyor,
    BuildingConveyor,
    BuildingFoundry,
    BuildingHarvester,
    BuildingRoad,
    BuildingSplitter,
)
from cambc import Direction, EntityType, Environment, Position
from util import DIR4, can_afford

from .helpers import make_move, try_place

if TYPE_CHECKING:
    from cambc import Controller

    from .state import State

MIN_ROUND: Final[int] = 500


def _has_ax_ore_known(state: State) -> bool:
    return any(env == Environment.ORE_AXIONITE for env in state.env)


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


def task_harvest_ax(state: State, ct: Controller) -> bool:
    if ct.get_current_round() < MIN_ROUND:
        return False
    if state.ore_target is not None:
        return False
    ax_target = _pick_ax_ore_target(state, ct)
    if ax_target is None:
        return False
    state.ore_target = ax_target
    make_move(state, ct, ax_target)
    return True


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


def _sees_raw_ax_near_core(state: State, ct: Controller) -> bool:
    from cambc import ResourceType

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


def task_place_splitter(state: State, ct: Controller) -> bool:
    if ct.get_current_round() < MIN_ROUND:
        return False
    if not _sees_raw_ax_near_core(state, ct):
        return False
    pair = _find_conv_for_splitter(state, ct)
    if pair is None:
        return False
    conv_pos, _fnd_pos = pair
    if ct.get_position().distance_squared(conv_pos) > 2:
        make_move(state, ct, conv_pos)
        return True
    bld = state.get_building(conv_pos)
    if isinstance(bld, (BuildingConveyor, BuildingArmouredConveyor)):
        input_dir = _detect_input_direction(state, conv_pos)
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
    if not _has_ax_ore_known(state):
        return False
    if not can_afford(ct, EntityType.FOUNDRY):
        return False
    pos = _find_foundry_site(state, ct)
    if pos is None:
        return False
    if ct.get_position().distance_squared(pos) > 2:
        make_move(state, ct, pos)
        return True
    try_place(ct, EntityType.FOUNDRY, pos)
    return True


def _pick_ax_ore_target(state: State, ct: Controller) -> Position | None:
    best: Position | None = None
    best_dist = float("inf")
    my_pos = ct.get_position()
    for pos in ct.get_nearby_tiles():
        if state.get_env(pos) != Environment.ORE_AXIONITE:
            continue
        match state.get_building(pos):
            case BuildingHarvester():
                continue
            case None | BuildingRoad():
                pass
            case _:
                continue
        bid = ct.get_tile_builder_bot_id(pos)
        if bid is not None and bid != ct.get_id():
            continue
        d = my_pos.distance_squared(pos)
        if d < best_dist:
            best_dist = d
            best = pos
    return best


def _has_ax_harvester(state: State, ct: Controller) -> bool:
    for i, bld in enumerate(state.buildings):
        if isinstance(bld, BuildingHarvester) and bld.team == ct.get_team():
            if state.env[i] == Environment.ORE_AXIONITE:
                return True
    return False


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
