"""Pure query functions on State. No mutation."""

from building import (
    BuildingArmouredConveyor,
    BuildingBreach,
    BuildingConveyor,
    BuildingCore,
    BuildingGunner,
    BuildingMarker,
    BuildingRoad,
    BuildingSentinel,
    BuildingSplitter,
)
from cambc import Direction, Environment, Position
from util import COST_EMPTY, COST_IMPASSABLE, COST_ROAD, COST_UNSEEN, Symmetry

from .state import State


def walkable(state: State, x: int, y: int) -> int:
    i = y * state.w + x
    if Position(x, y) in state.unit_tiles:
        return COST_IMPASSABLE
    match state.env[i]:
        case None:
            return COST_UNSEEN
        case Environment.WALL | Environment.ORE_TITANIUM | Environment.ORE_AXIONITE:
            return COST_IMPASSABLE
    match state.building[i]:
        case None | BuildingMarker():
            return COST_EMPTY
        case BuildingCore(team) if team == state.my_team:
            return COST_ROAD
        case (
            BuildingRoad()
            | BuildingConveyor()
            | BuildingArmouredConveyor()
            | BuildingSplitter()
        ):
            return COST_ROAD
        case _:
            return COST_IMPASSABLE


def in_bounds(state: State, x: int, y: int) -> bool:
    return 0 <= x < state.w and 0 <= y < state.h


def is_passable(state: State, x: int, y: int) -> bool:
    return in_bounds(state, x, y) and walkable(state, x, y) < COST_IMPASSABLE


def is_unseen(state: State, x: int, y: int) -> bool:
    return state.env[y * state.w + x] is None


def mirror(state: State, p: Position) -> Position:
    x, y = p
    match state.symmetry:
        case Symmetry.ROT:
            return Position(state.w - 1 - x, state.h - 1 - y)
        case Symmetry.HOR:
            return Position(x, state.h - 1 - y)
        case Symmetry.VER:
            return Position(state.w - 1 - x, y)
        case None:
            return Position(x, y)


def accepts_input_from(state: State, ti: int, from_dir: Direction) -> bool:
    bld = state.building[ti]
    if bld is None:
        return True
    match bld:
        case BuildingSplitter(direction=d):
            return from_dir == d
        case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
            return from_dir != d.opposite()
        case (
            BuildingGunner(direction=d)
            | BuildingSentinel(direction=d)
            | BuildingBreach(direction=d)
        ):
            # Turrets receive from non-facing sides. from_dir is flow travel direction,
            # so entry side is from_dir.opposite(). Reject if entry side == facing.
            return from_dir != d.opposite()
    return True


def harvester_ore_type(state: State, i: int) -> Environment | None:
    if i in state.ore_ti:
        return Environment.ORE_TITANIUM
    if i in state.ore_ax:
        return Environment.ORE_AXIONITE
    return None
