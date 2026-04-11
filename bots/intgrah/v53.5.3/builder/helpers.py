from building import (
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingHarvester,
    BuildingRoad,
    BuildingSplitter,
)
from cambc import Controller, Direction, EntityType, Environment, Position
from util import DIR4, DIR8, INF, Symmetry, can_afford, closest, try_move

from builder.algorithms.astar import pathfind_move
from builder.state import State


def make_move(state: State, ct: Controller, target: Position) -> bool:
    if ct.get_position() == target:
        return True

    next_pos = pathfind_move(state, ct, ct.get_position(), target)
    if next_pos is not None:
        try_move_with_build(state, ct, next_pos)
        return True
    return False


def try_move_with_road(ct: Controller, target_pos: Position, state: State) -> bool:
    if state.get_cost(target_pos) > 2 and ct.can_build_road(target_pos):
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
        i = state.idx(state.repair_pos)
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


def ore_available(state: State, ct: Controller, pos: Position) -> bool:
    b = state.get_building(pos)
    if b is not None and not isinstance(b, BuildingRoad):
        return False

    if ct.is_in_vision(pos):
        worker_id = ct.get_tile_builder_bot_id(pos)
        if worker_id is not None and worker_id != ct.get_id():
            return False

    return True


def pick_ore_target(state: State, ct: Controller) -> Position | None:
    w = state.w
    nav_dist = state.bfs_dist

    best_target = None
    min_dist = INF

    for pos in ct.get_nearby_tiles():
        terrain = state.get_env(pos)

        if terrain == Environment.ORE_TITANIUM or (
            terrain == Environment.ORE_AXIONITE and ct.get_current_round() >= 500
        ):
            match state.get_building(pos):
                case BuildingHarvester():
                    continue
                case None | BuildingRoad():
                    pass
                case _:
                    continue

            d = nav_dist[pos.y * w + pos.x]
            if d == -1:
                continue

            if ore_available(state, ct, pos) and d < min_dist:
                min_dist = d
                best_target = pos

    return best_target


def is_dangling(state: State, ct: Controller, pos: Position) -> bool:
    if not state.in_bounds(pos):
        return False

    i = pos.y * state.w + pos.x
    b = state.buildings[i]
    if b is None:
        if state.env[i] == Environment.WALL:
            return False

    elif not isinstance(b, BuildingRoad) or b.team != ct.get_team():
        return False

    if state.conveyors_to_here[i]:
        return True

    return (
        pos in state.adjacent_to_unconnected_harvester
        or pos in state.adjacent_to_unconnected_foundry
    )


def is_valid_loose_end_target(state: State, ct: Controller, pos: Position) -> bool:
    if not is_dangling(state, ct, pos):
        return False

    my_id = ct.get_id()
    if ct.is_in_vision(pos):
        bid = ct.get_tile_builder_bot_id(pos)
        friendly = ct.get_team(bid) == ct.get_team()
        if bid is not None and bid != my_id and friendly:
            return False

    leading = state.get_conveyors_to_here(pos)
    for lpos in leading:
        if not ct.is_in_vision(lpos):
            continue
        lbid = ct.get_tile_builder_bot_id(lpos)
        friendly = ct.get_team(lbid) == ct.get_team()
        if lbid is not None and lbid != my_id and friendly:
            return False
    return True


def find_dangling(state: State, ct: Controller) -> Position | None:
    w = state.w
    nav_dist = state.bfs_dist
    vision_radius = ct.get_vision_radius_sq()
    nearby = ct.get_nearby_tiles(vision_radius)

    candidates = [
        pos
        for pos in nearby
        if is_valid_loose_end_target(state, ct, pos)
        and nav_dist[pos.y * w + pos.x] != -1
    ]

    if not candidates:
        return None

    my_pos = ct.get_position()
    return closest(my_pos, candidates)
