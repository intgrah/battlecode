from __future__ import annotations

from typing import TYPE_CHECKING

from building import BuildingConveyor, BuildingSplitter
from cambc import Controller, Direction, EntityType, Environment, Position
from util import (
    DIR4,
    DIR8,
    can_afford,
    chebyshev,
    get_direction_object,
    reachable_path_end,
)

from builder.algorithms.econ_astar import conv_search
from builder.helpers import (
    is_enemy_building,
    make_move,
    trace_upstream,
    try_move_with_road,
    try_place,
)
from builder.update.econ import can_place_junction

if TYPE_CHECKING:
    from builder import Builder


def clear_with_turret(
    self: Builder,
    ct: Controller,
    build_pos: Position,
    target_pos: Position,
) -> bool:
    if build_pos == ct.get_position():
        for d in DIR8:
            if ct.can_move(d):
                ct.move(d)
                break

    if build_pos == ct.get_position():
        for d in DIR8:
            move_pos = ct.get_position().add(d)
            if try_move_with_road(self, ct, move_pos):
                break

    direction = build_pos.direction_to(target_pos)
    return try_place(ct, EntityType.SENTINEL, build_pos, direction)


def lay_segment(
    ct: Controller,
    start_pos: Position,
    path: list[Position] | None,
    self: Builder,
) -> bool:
    if not path:
        return False

    bid = ct.get_tile_building_id(start_pos)
    entity_type = ct.get_entity_type(bid) if bid else None
    direction: Direction | None = None
    if (
        self.my_core
        and start_pos.distance_squared(self.my_core) <= 5
        and path[-1] == self.my_core
    ):
        for d in DIR4:
            check_pos = start_pos.add(d)
            if check_pos.distance_squared(self.my_core) <= 2:
                direction = d
                break
    else:
        direction = get_direction_object(start_pos, path[1])

    if entity_type == EntityType.CONVEYOR:
        if ct.get_direction(bid) == direction:
            return True
    elif entity_type == EntityType.BRIDGE:
        bridge_output = ct.get_bridge_target(bid)
        if not ct.is_in_vision(bridge_output) or self.is_buildable(bridge_output):
            return True

    next_pos = path[1]
    if not ct.is_in_vision(next_pos):
        return try_place(
            ct,
            EntityType.BRIDGE,
            start_pos,
            reachable_path_end(path, start_pos, 3),
        )
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
            (not destination_building)
            or destination_team == ct.get_team()
            or destination_is_marker
        )
        and self.get_env(path[1]) == Environment.EMPTY
    ):
        return try_place(ct, EntityType.CONVEYOR, start_pos, direction)
    pending_bridge = reachable_path_end(path, start_pos, 3)
    if is_enemy_building(self, ct, pending_bridge):
        if clear_with_turret(self, ct, start_pos, pending_bridge):
            self.branch_start = start_pos
        return False
    if try_place(ct, EntityType.BRIDGE, start_pos, pending_bridge):
        if chebyshev(pending_bridge, self.my_core) > 1:
            self.pending_bridge = pending_bridge
        return True
    return False


def best_junction_site(
    self: Builder,
    ct: Controller,
    path: list[Position],
) -> Position | None:
    for pos in path[::-1]:
        if can_place_junction(self, ct, pos):
            return pos
    return None


def place_junction(self: Builder, ct: Controller, pos: Position) -> bool | None:
    current_building = self.get_building(pos)
    if isinstance(current_building, BuildingSplitter):
        return True

    for d in DIR4:
        new_pos = pos.add(d)
        existing_building = self.get_building(new_pos)
        if (
            (self.get_env(new_pos) == Environment.EMPTY)
            and existing_building is None
            and ct.can_build_road(new_pos)
        ):
            ct.build_road(new_pos)
            return False

    conveyors = self.get_conveyors_to_here(pos)
    adjacent_conveyors = [c for c in conveyors if c.distance_squared(pos) <= 1]
    if len(adjacent_conveyors) > 1 or len(conveyors) < 1:
        return False
    if len(adjacent_conveyors) >= 1:
        splitter_direction = adjacent_conveyors[0].direction_to(pos)
    elif isinstance(bld_at_pos := self.get_building(pos), BuildingConveyor):
        splitter_direction = bld_at_pos.direction
    else:
        splitter_direction = Direction.NORTH

    if not can_afford(ct, EntityType.SPLITTER):
        return False
    if ct.can_destroy(pos):
        ct.destroy(pos)
    if ct.can_build_splitter(pos, splitter_direction):
        ct.build_splitter(pos, splitter_direction)
        return True
    return None


def route_to(
    self: Builder,
    ct: Controller,
    start: Position,
    target: Position,
) -> None:
    self.pending_bridge = None
    self.branch_start = None

    if start == target:
        return

    if chebyshev(start, target) <= 1 and target == self.my_core:
        return

    current_pos = ct.get_position()

    start_building = self.get_building(start)
    all_blocked = True
    if isinstance(start_building, BuildingSplitter):
        for d in DIR4:
            if d == start_building.direction.opposite():
                continue
            new_pos = start.add(d)
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
        if split_location:
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

    path = conv_search.search(self, ct, start, target)
    if path:
        path_start_index = 0
        for i, pos in enumerate(path):
            if pos in existing_path:
                start = pos
                path_start_index = i
        path = path[path_start_index:]

    if chebyshev(current_pos, start) <= 1:
        if not path or (conv_search.unreachable(target) and not path) or len(path) < 2:
            return
        lay_segment(ct, start, path, self)
    make_move(self, ct, start)
    return


def route_to_core(self: Builder, ct: Controller, start: Position) -> None:
    return route_to(self, ct, start, self.my_core)
