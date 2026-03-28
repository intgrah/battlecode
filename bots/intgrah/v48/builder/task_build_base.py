from base_layout import base_layout, execution_cells
from building import (
    BuildingBarrier,
    BuildingBridge,
    BuildingGunner,
    BuildingLauncher,
    BuildingRoad,
    BuildingSplitter,
)
from cambc import Controller, Direction, Position

from .build import (
    Action,
    PlaceBarrier,
    PlaceBridge,
    PlaceGunner,
    PlaceLauncher,
    PlaceRoad,
    PlaceSplitter,
)
from .helpers import move_toward
from .state import State


def build_base(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    pos = state.pos
    plan = base_layout(state.my_core, state.my_team)

    for target_pos, spec in plan:
        if not state.in_bounds(target_pos.x, target_pos.y):
            continue
        i = state.idx(target_pos.x, target_pos.y)
        existing = state.building[i]
        if existing is not None and isinstance(existing, type(spec)):
            continue

        action = _to_action(target_pos, spec)
        if action is None:
            continue

        if pos == target_pos:
            adj = _step_off(state, pos)
            if adj is not None:
                d = move_toward(state, ct, adj)
                return d, None
            return Direction.CENTRE, None

        if pos.distance_squared(target_pos) <= 2:
            return Direction.CENTRE, action

        d = move_toward(state, ct, target_pos)
        if d != Direction.CENTRE:
            state.debug_target = (target_pos, 128, 128, 255)
            return d, None
        return None

    return None


def repair_execution_cells(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    pos = state.pos
    for cell in execution_cells(state.my_core):
        if not state.in_bounds(cell.x, cell.y):
            continue
        i = state.idx(cell.x, cell.y)
        bld = state.building[i]
        if isinstance(bld, BuildingRoad):
            continue
        if pos == cell:
            adj = _step_off(state, pos)
            if adj is not None:
                d = move_toward(state, ct, adj)
                return d, None
            return Direction.CENTRE, None
        if pos.distance_squared(cell) <= 2:
            return Direction.CENTRE, PlaceRoad(cell)
        d = move_toward(state, ct, cell)
        if d != Direction.CENTRE:
            state.debug_target = (cell, 255, 128, 128)
            return d, None
    return None


def _step_off(state: State, pos: Position) -> Position | None:
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            if dx == 0 and dy == 0:
                continue
            nx, ny = pos.x + dx, pos.y + dy
            if not state.in_bounds(nx, ny):
                continue
            p = Position(nx, ny)
            if p in state.my_core_tiles:
                return p
    return None


def _to_action(
    pos: Position,
    spec: BuildingBarrier
    | BuildingBridge
    | BuildingGunner
    | BuildingLauncher
    | BuildingRoad
    | BuildingSplitter,
) -> Action | None:
    match spec:
        case BuildingBarrier():
            return PlaceBarrier(pos)
        case BuildingRoad():
            return PlaceRoad(pos)
        case BuildingGunner(direction=d):
            return PlaceGunner(pos, d)
        case BuildingSplitter(direction=d):
            return PlaceSplitter(pos, d)
        case BuildingLauncher():
            return PlaceLauncher(pos)
        case BuildingBridge(target=t):
            return PlaceBridge(pos, t)
    return None
