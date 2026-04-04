
from building import BuildingConveyor, BuildingHarvester, BuildingSplitter
from cambc import Controller, Direction, EntityType, Position
from marker import TaskKind
from navigation import find_path
from util import COST_IMPASSABLE, DIR4, DIR4_DELTA, INF

from .action import (
    Action,
    PlaceArmouredConveyor,
    PlaceBarrier,
    PlaceBridge,
    PlaceConveyor,
    PlaceFoundry,
    PlaceHarvester,
    PlaceRoad,
    PlaceSplitter,
    SelfDestruct,
)
from .state import State


def move_toward(state: State, ct: Controller, target: Position) -> Direction:
    pos = state.pos
    if pos == target:
        return Direction.CENTRE
    path = find_path(state, target.x, target.y)
    if path is None or len(path) < 2:
        return Direction.CENTRE
    draw_path(ct, state.w, path)
    w = state.w
    nx, ny = path[1] % w, path[1] // w
    nxt = Position(nx, ny)
    d = pos.direction_to(nxt)
    if ct.can_move(d):
        return d
    return Direction.CENTRE


def move_toward_with_road(
    state: State,
    ct: Controller,
    target: Position,
) -> tuple[Direction, Action | None]:
    pos = state.pos
    if pos == target:
        return Direction.CENTRE, None
    path = find_path(state, target.x, target.y)
    if path is None or len(path) < 2:
        return Direction.CENTRE, None
    draw_path(ct, state.w, path)
    w = state.w
    nx, ny = path[1] % w, path[1] // w
    nxt = Position(nx, ny)
    d = pos.direction_to(nxt)
    if ct.can_move(d):
        return d, None
    road_cost, _ = ct.get_road_cost()
    ti, _ = ct.get_global_resources()
    if ti >= road_cost and ct.can_build_road(nxt):
        return d, PlaceRoad(nxt)
    return Direction.CENTRE, None


def draw_path(
    ct: Controller,
    w: int,
    path: list[int],
    colour: tuple[int, int, int] = (255, 255, 255),
) -> None:
    pass


def cardinal_adjacent(state: State, pos: Position, target: Position) -> Position | None:
    best = None
    best_dist = INF
    for ddx, ddy in DIR4_DELTA:
        ax, ay = target.x + ddx, target.y + ddy
        if not state.in_bounds(ax, ay):
            continue
        if state.walkable(ax, ay) >= COST_IMPASSABLE:
            continue
        dist = (pos.x - ax) ** 2 + (pos.y - ay) ** 2
        if dist < best_dist:
            best_dist = dist
            best = Position(ax, ay)
    return best


def step_off_and_build(
    ct: Controller,
    build: Action,
) -> tuple[Direction, Action] | None:
    """Step off the current tile so an impassable building can be placed.

    If an adjacent tile is walkable, move there and build in one turn.
    If not, place a road on an adjacent tile — next turn we can step off.
    """
    from util import DIR8

    pos = ct.get_position()
    for d in DIR8:
        if ct.can_move(d):
            return d, build
    # No walkable neighbor — pave a road so we can step off next turn
    for d in DIR8:
        adj = pos.add(d)
        if ct.can_build_road(adj):
            return Direction.CENTRE, PlaceRoad(adj)
    return None


def is_claimed(state: State, tile_index: int, kind: TaskKind) -> bool:
    # Don't filter FIX_EXCESS — excess tiles shift as conveyors are built,
    # so claims on the old tile block the new one. Multiple builders working
    # on the same excess is fine.
    if kind == TaskKind.FIX_EXCESS:
        return False
    for c in state.claims:
        if c.tile_index == tile_index and c.kind == kind:
            if (
                state.last_claim is not None
                and c.tile_index == state.last_claim.tile_index
                and c.kind == state.last_claim.kind
            ):
                continue
            return True
    return False


def _destroy_friendly(ct: Controller, pos: Position) -> None:
    """Destroy low-value friendly buildings (roads, markers) to make room."""
    bid = ct.get_tile_building_id(pos)
    if bid is None:
        return
    if ct.get_team(bid) != ct.get_team():
        return
    if ct.get_entity_type(bid) in (EntityType.ROAD, EntityType.MARKER):
        if ct.can_destroy(pos):
            ct.destroy(pos)


def _destroy_any_friendly(ct: Controller, pos: Position) -> None:
    """Destroy any friendly building to make room for a replacement."""
    bid = ct.get_tile_building_id(pos)
    if bid is None:
        return
    if ct.get_team(bid) != ct.get_team():
        return
    if ct.can_destroy(pos):
        ct.destroy(pos)


def execute(action: Action, ct: Controller) -> None:
    ti, _ = ct.get_global_resources()
    match action:
        case PlaceHarvester(pos):
            cost, _ = ct.get_harvester_cost()
            if ti >= cost:
                _destroy_friendly(ct, pos)
                if ct.can_build_harvester(pos):
                    ct.build_harvester(pos)
        case PlaceConveyor(pos, direction):
            cost, _ = ct.get_conveyor_cost()
            if ti >= cost:
                _destroy_friendly(ct, pos)
                if ct.can_build_conveyor(pos, direction):
                    ct.build_conveyor(pos, direction)
        case PlaceArmouredConveyor(pos, direction):
            cost, _ = ct.get_armoured_conveyor_cost()
            if ti >= cost:
                _destroy_friendly(ct, pos)
                if ct.can_build_armoured_conveyor(pos, direction):
                    ct.build_armoured_conveyor(pos, direction)
        case PlaceBridge(pos, target):
            cost, _ = ct.get_bridge_cost()
            if ti >= cost:
                _destroy_friendly(ct, pos)
                if ct.can_build_bridge(pos, target):
                    ct.build_bridge(pos, target)
        case PlaceRoad(pos):
            cost, _ = ct.get_road_cost()
            if ti >= cost and ct.can_build_road(pos):
                ct.build_road(pos)
        case PlaceFoundry(pos):
            cost, _ = ct.get_foundry_cost()
            if ti >= cost:
                _destroy_friendly(ct, pos)
                if ct.can_build_foundry(pos):
                    ct.build_foundry(pos)
        case PlaceSplitter(pos, direction):
            cost, _ = ct.get_splitter_cost()
            if ti >= cost:
                _destroy_any_friendly(ct, pos)
                if ct.can_build_splitter(pos, direction):
                    ct.build_splitter(pos, direction)
        case SelfDestruct():
            ct.self_destruct()
        case PlaceBarrier(pos):
            cost, _ = ct.get_barrier_cost()
            if ti >= cost:
                _destroy_friendly(ct, pos)
                if ct.can_build_barrier(pos):
                    ct.build_barrier(pos)


def flow_from_back(state: State, idx: int, splitter_dir: Direction) -> float:
    """How much Ti flow a splitter at idx facing splitter_dir would receive.

    A splitter accepts only from its back (opposite of facing).
    """
    w = state.w
    cx, cy = idx % w, idx // w
    bdx, bdy = splitter_dir.opposite().delta()
    bx, by = cx + bdx, cy + bdy
    if not state.in_bounds(bx, by):
        return 0.0
    bi = by * w + bx
    nbld = state.building[bi]
    match nbld:
        case BuildingConveyor(direction=nd) | BuildingSplitter(direction=nd):
            ddx, ddy = nd.delta()
            if (bx + ddx, by + ddy) == (cx, cy):
                return state.flow.ti[bi]
        case BuildingHarvester():
            return state.flow.ti[bi]
    return 0.0


def valid_splitter_orientations(
    state: State,
    idx: int,
    prev_flow: float,
) -> list[Direction]:
    """Return splitter orientations that preserve flow >= min(prev_flow, 1)."""
    threshold = min(prev_flow, 1.0)
    valid: list[Direction] = []
    for d in DIR4:
        received = flow_from_back(state, idx, d)
        if received >= threshold:
            valid.append(d)
    return valid
