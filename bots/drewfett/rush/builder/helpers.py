from building import BuildingConveyor, BuildingHarvester, BuildingSplitter
from cambc import Controller, Direction, EntityType, Position
from marker import TaskKind
from util import COST_IMPASSABLE, DIR4, DIR4_DELTA, INF

from .action import (
    Action,
    Fire,
    Heal,
    PlaceArmouredConveyor,
    PlaceBarrier,
    PlaceBridge,
    PlaceConveyor,
    PlaceFoundry,
    PlaceGunner,
    PlaceHarvester,
    PlaceLauncher,
    PlaceRoad,
    PlaceSentinel,
    PlaceSplitter,
    SelfDestruct,
)
from .state import State

_BFS_DIRECTIONS: tuple[Direction, ...] = (
    Direction.NORTHEAST,
    Direction.SOUTHEAST,
    Direction.SOUTHWEST,
    Direction.NORTHWEST,
    Direction.NORTH,
    Direction.EAST,
    Direction.SOUTH,
    Direction.WEST,
)


def move_toward_with_road(
    state: State,
    ct: Controller,
    target: Position,
) -> tuple[Direction, Action | None]:
    pos = state.pos
    if pos == target:
        return Direction.CENTRE, None

    nav = state.nav_bfs
    if nav is None:
        return Direction.CENTRE, None

    nav.set_goal(target)
    weights = nav.step(pos, lambda: ct.get_cpu_time_elapsed() < 1400)

    if weights == (0, 0, 0, 0, 0, 0, 0, 0):
        return Direction.CENTRE, None

    # Sort by weight. Break ties: prefer cardinal over diagonal, then by distance to target.
    tx, ty = target.x, target.y
    _DELTAS = ((1, -1), (1, 1), (-1, 1), (-1, -1), (0, -1), (1, 0), (0, 1), (-1, 0))
    _IS_DIAG = (1, 1, 1, 1, 0, 0, 0, 0)
    indexed = []
    for i in range(8):
        w = weights[i]
        if w >= INF:
            continue
        ddx, ddy = _DELTAS[i]
        nx, ny = pos.x + ddx, pos.y + ddy
        dist_sq = (nx - tx) ** 2 + (ny - ty) ** 2
        indexed.append((w, _IS_DIAG[i], dist_sq, i))
    indexed.sort()

    if not indexed:
        return Direction.CENTRE, None

    # For each direction (best first): try move, then road
    # BFS grid already marks launchers as impassable (weight=INF)
    # Also skip gunner/sentinel arcs (danger_zones) as soft avoid
    road_cost, _ = ct.get_road_cost()
    ti_res, _ = ct.get_global_resources()
    w = state.w
    danger = state.danger_zones
    for _w, _d, _ds, i in indexed:
        d = _BFS_DIRECTIONS[i]
        nxt = pos.add(d)
        ni = nxt.y * w + nxt.x
        if ni in danger:
            continue
        if ct.can_move(d):
            return d, None
        if ti_res >= road_cost and ct.can_build_road(nxt):
            return d, PlaceRoad(nxt)

    # All directions blocked or dangerous — try without danger check as last resort
    for _w, _d, _ds, i in indexed:
        d = _BFS_DIRECTIONS[i]
        if ct.can_move(d):
            return d, None

    return Direction.CENTRE, None


def cardinal_adjacent(state: State, pos: Position, target: Position) -> Position | None:
    """Pick a walkable tile adjacent to target. Deterministic: always picks the
    same tile regardless of builder position (closest to core) to prevent oscillation."""
    core = state.my_core
    best = None
    best_dist = INF
    for ddx, ddy in DIR4_DELTA:
        ax, ay = target.x + ddx, target.y + ddy
        if not state.in_bounds(ax, ay):
            continue
        if state.walkable(ax, ay) >= COST_IMPASSABLE:
            continue
        # Deterministic: closest to core, not to builder
        dist = (core.x - ax) ** 2 + (core.y - ay) ** 2
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
        case PlaceGunner(pos, direction):
            cost, _ = ct.get_gunner_cost()
            if ti >= cost:
                _destroy_friendly(ct, pos)
                if ct.can_build_gunner(pos, direction):
                    ct.build_gunner(pos, direction)
        case Fire():
            pos = ct.get_position()
            if ct.can_fire(pos):
                ct.fire(pos)


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
