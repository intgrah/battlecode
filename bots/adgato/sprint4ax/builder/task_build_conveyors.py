from __future__ import annotations

from typing import TYPE_CHECKING

from building import BuildingConveyor, BuildingSplitter
from cambc import Controller, EntityType, Environment, Direction
from util import (
    DIR4,
    DIR8,
    DELTA_TO_DIR,
    DIR_TO_DELTA,
    get_direction_object,
    reachable_path_end,
)

from .algorithms.pathfind import conv_pathfind, conv_unreachable
from .helpers import (
    is_enemy_building,
    make_move,
    trace_upstream,
    try_move_with_road,
    try_place,
)
from .update.map import can_place_junction

if TYPE_CHECKING:
    from builder import Builder, PosInt


def clear_with_turret(
    self: Builder, ct: Controller, build_pos: PosInt, target_pos: PosInt
) -> bool:
    if build_pos == self.my_pos:
        for d in DIR8:
            if ct.can_move(DELTA_TO_DIR[d]):
                ct.move(DELTA_TO_DIR[d])
                break

    if build_pos == self.my_pos:
        for d in DIR8:
            move_pos = self.my_pos + d
            if try_move_with_road(self, ct, move_pos):
                break

    direction = get_direction_object(build_pos, target_pos)
    return try_place(ct, EntityType.SENTINEL, self.pos(build_pos), direction)


def lay_segment(
    ct: Controller,
    start_pos: PosInt,
    path: list[PosInt] | None,
    self: Builder,
) -> bool:
    if not path:
        return False

    building_id = ct.get_tile_building_id(self.pos(start_pos))
    entity_type = ct.get_entity_type(building_id) if building_id else None

    direction = 0

    if (
        self.my_core >= 0
        and self.sq_dist(start_pos, self.my_core) <= 5
        and path[-1] == self.my_core
    ):
        for d in DIR4:
            check_pos = start_pos + d
            if self.sq_dist(check_pos, self.my_core) <= 2:
                direction = d
                break
    else:
        direction = DIR_TO_DELTA[get_direction_object(start_pos, path[1])]

    if entity_type == EntityType.CONVEYOR:
        if direction != 0 and ct.get_direction(building_id) == DELTA_TO_DIR[direction]:
            return True
    elif building_id is not None and entity_type == EntityType.BRIDGE:
        bridge_output = ct.get_bridge_target(building_id)
        if not ct.is_in_vision(bridge_output) or self.is_buildable(
            self._idx(bridge_output)
        ):
            return True

    next_pos = self.pos(path[1])
    if not ct.is_in_vision(next_pos):
        target = reachable_path_end(self, path, start_pos, 3)
        if start_pos != target:
            return try_place(
                ct, EntityType.BRIDGE, self.pos(start_pos), self.pos(target)
            )
        return False
    destination_building = ct.get_tile_building_id(next_pos)
    destination_team = (
        ct.get_team(destination_building) if destination_building else None
    )
    destination_is_marker = (
        ct.get_entity_type(destination_building) == EntityType.MARKER
        if destination_building
        else False
    )

    if (
        direction in DIR4
        and (
            destination_building is None
            or destination_team == self.my_team
            or destination_is_marker
        )
        and self.get_env(path[1]) != Environment.WALL
    ):
        return try_place(
            ct, EntityType.CONVEYOR, self.pos(start_pos), DELTA_TO_DIR[direction]
        )
    pending_bridge = reachable_path_end(self, path, start_pos, 3)
    if is_enemy_building(self, ct, pending_bridge):
        if clear_with_turret(self, ct, start_pos, pending_bridge):
            self.branch_start = start_pos
        return False
    if start_pos != pending_bridge and try_place(
        ct, EntityType.BRIDGE, self.pos(start_pos), self.pos(pending_bridge)
    ):
        if self.sq_dist(pending_bridge, self.my_core) > 2:
            self.pending_bridge = pending_bridge
        return True
    return False


def best_junction_site(self: Builder, ct: Controller, path: list[PosInt]) -> PosInt:
    for pos in path[::-1]:
        if can_place_junction(self, ct, pos):
            return pos
    return -1


def place_junction(self: Builder, ct: Controller, pos: PosInt) -> bool | None:
    current_building = self.get_building(pos)
    if isinstance(current_building, BuildingSplitter):
        return True

    for d in DIR4:
        new_pos = pos + d
        existing_building = self.get_building(new_pos)
        if (
            (self.get_env(new_pos) == Environment.EMPTY)
            and existing_building is None
            and ct.can_build_road(self.pos(new_pos))
        ):
            ct.build_road(self.pos(new_pos))
            return False

    conveyors = self.get_conveyors_to_here(pos)
    adjacent_conveyors = [c for c in conveyors if self.sq_dist(c, pos) <= 1]
    if len(adjacent_conveyors) > 1 or len(conveyors) < 1:
        return False
    if len(adjacent_conveyors) >= 1:
        splitter_direction = self.sq_dist(adjacent_conveyors[0], pos)
    elif isinstance(bld_at_pos := self.get_building(pos), BuildingConveyor):
        splitter_direction = bld_at_pos.direction
    else:
        splitter_direction = DIR_TO_DELTA[Direction.NORTH]

    return try_place(
        ct, EntityType.SPLITTER, self.pos(pos), DELTA_TO_DIR[splitter_direction]
    )


def route_to(
    self: Builder,
    ct: Controller,
    start: PosInt,
    target: PosInt,
) -> None:
    self.pending_bridge = -1
    self.branch_start = -1

    if start == target:
        return

    if self.sq_dist(start, target) <= 2 and target == self.my_core:
        return

    start_building = self.get_building(start)
    all_blocked = True
    if isinstance(start_building, BuildingSplitter):
        for d in DIR4:
            if d == -start_building.direction:
                continue
            new_pos = start + d
            if self.is_buildable(new_pos):
                start = new_pos
                all_blocked = False
                break
    else:
        all_blocked = False

    existing_path = trace_upstream(self, start)
    if len(existing_path) < 1:
        return

    if self.is_friendly_turret(start) or all_blocked:
        split_location = best_junction_site(self, ct, existing_path)
        if split_location >= 0:
            make_move(self, ct, split_location)
            if place_junction(self, ct, split_location):
                self.branch_start = split_location
            else:
                self.branch_start = start
        return

    if not self.is_passable(start):
        if len(existing_path) > 1:
            start = existing_path[-2]
        else:
            return

    path = [
        self._idx(p) for p in conv_pathfind(self, ct, self.pos(start), self.pos(target))
    ]
    self.dump_path = path
    if path:
        path_start_index = 0
        for i, pos in enumerate(path):
            if pos in existing_path:
                start = pos
                path_start_index = i
        path = path[path_start_index:]

    if self.my_sq_dist(start) <= 2:
        if (
            not path
            or (conv_unreachable(self.pos(target)) and not path)
            or len(path) < 2
        ):
            return
        lay_segment(ct, start, path, self)
    make_move(self, ct, start)


def route_to_core(self: Builder, ct: Controller, start: PosInt) -> None:
    return route_to(self, ct, start, self.my_core)
