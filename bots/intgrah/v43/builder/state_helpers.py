"""Pure query functions on State. No mutation."""

from cambc import Direction, EntityType, Environment
from util import WALKABLE_BUILDINGS

from .state import COST_EMPTY, COST_IMPASSABLE, COST_ROAD, COST_UNSEEN, State, Symmetry


def walkable(state: State, x: int, y: int) -> int:
    i = y * state.w + x
    if i in state.unit_tiles:
        return COST_IMPASSABLE
    match state.env[i]:
        case None:
            return COST_UNSEEN
        case Environment.WALL | Environment.ORE_TITANIUM | Environment.ORE_AXIONITE:
            return COST_IMPASSABLE
    match state.entity[i]:
        case None:
            return COST_EMPTY
        case (EntityType.MARKER, _):
            return COST_EMPTY
        case (EntityType.CORE, team) if team == state.my_team:
            return COST_ROAD
        case (etype, _) if etype in WALKABLE_BUILDINGS:
            return COST_ROAD
        case _:
            return COST_IMPASSABLE


def in_bounds(state: State, x: int, y: int) -> bool:
    return 0 <= x < state.w and 0 <= y < state.h


def is_passable(state: State, x: int, y: int) -> bool:
    return in_bounds(state, x, y) and walkable(state, x, y) < COST_IMPASSABLE


def is_unseen(state: State, x: int, y: int) -> bool:
    return state.env[y * state.w + x] is None


def mirror(state: State, x: int, y: int) -> tuple[int, int]:

    match state.symmetry:
        case Symmetry.ROT:
            return state.w - 1 - x, state.h - 1 - y
        case Symmetry.HOR:
            return x, state.h - 1 - y
        case Symmetry.VER:
            return state.w - 1 - x, y
        case _:
            return x, y


def accepts_input_from(state: State, ti: int, from_dir: Direction) -> bool:
    ent = state.entity[ti]
    if ent is None:
        return True
    etype = ent[0]
    d = state.direction[ti]
    if etype == EntityType.SPLITTER:
        if d is None:
            return False
        return from_dir == d
    if etype in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR):
        if d is None:
            return True
        return from_dir != d.opposite()
    return True


def harvester_ore_type(state: State, i: int) -> Environment | None:
    x, y = i % state.w, i // state.w
    if (x, y) in state.ore_ti:
        return Environment.ORE_TITANIUM
    if (x, y) in state.ore_ax:
        return Environment.ORE_AXIONITE
    return None
