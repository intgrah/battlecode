import itertools

from cambc import Controller, Direction, EntityType, Position
from marker import TaskKind
from navigation import find_path
from util import COST_IMPASSABLE, INF

from .action import (
    Action,
    Fire,
    Heal,
    PlaceArmouredConveyor,
    PlaceBarrier,
    PlaceBridge,
    PlaceConveyor,
    PlaceFoundry,
    PlaceHarvester,
    PlaceLauncher,
    PlaceRoad,
    PlaceSentinel,
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
    _draw_path(ct, state.w, path)
    w = state.w
    nx, ny = path[1] % w, path[1] // w
    nxt = Position(nx, ny)
    d = pos.direction_to(nxt)
    if ct.can_move(d):
        return d
    return Direction.CENTRE


def move_toward_with_road(
    state: State, ct: Controller, target: Position
) -> tuple[Direction, Action | None]:
    pos = state.pos
    if pos == target:
        return Direction.CENTRE, None
    path = find_path(state, target.x, target.y)
    if path is None or len(path) < 2:
        return Direction.CENTRE, None
    _draw_path(ct, state.w, path)
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


def _draw_path(ct: Controller, w: int, path: list[int]) -> None:
    for u, v in itertools.pairwise(path):
        y0, x0 = divmod(u, w)
        y1, x1 = divmod(v, w)
        ct.draw_indicator_line(Position(x0, y0), Position(x1, y1), 0, 0, 0)


def cardinal_adjacent(state: State, pos: Position, target: Position) -> Position | None:
    best = None
    best_dist = INF
    for ddx, ddy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
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


def is_claimed(state: State, tile_index: int, kind: TaskKind) -> bool:
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
    bid = ct.get_tile_building_id(pos)
    if bid is None:
        return
    if ct.get_team(bid) != ct.get_team():
        return
    if ct.get_entity_type(bid) in (EntityType.ROAD, EntityType.MARKER):
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
                _destroy_friendly(ct, pos)
                if ct.can_build_splitter(pos, direction):
                    ct.build_splitter(pos, direction)
        case SelfDestruct():
            ct.self_destruct()
        case Heal(pos):
            if ct.can_heal(pos):
                ct.heal(pos)
        case PlaceBarrier(pos):
            cost, _ = ct.get_barrier_cost()
            if ti >= cost:
                _destroy_friendly(ct, pos)
                if ct.can_build_barrier(pos):
                    ct.build_barrier(pos)
        case PlaceSentinel(pos, direction):
            cost, _ = ct.get_sentinel_cost()
            if ti >= cost:
                _destroy_friendly(ct, pos)
                if ct.can_build_sentinel(pos, direction):
                    ct.build_sentinel(pos, direction)
        case PlaceLauncher(pos):
            cost, _ = ct.get_launcher_cost()
            if ti >= cost:
                _destroy_friendly(ct, pos)
                if ct.can_build_launcher(pos):
                    ct.build_launcher(pos)
        case Fire():
            pos = ct.get_position()
            if ct.can_fire(pos):
                ct.fire(pos)
