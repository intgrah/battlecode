# ruff: noqa: A002
from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import (
    Controller,
    Direction,
    EntityType,
    Environment,
    Position,
    ResourceType,
    Team,
)

if TYPE_CHECKING:
    from collections.abc import Callable


class Saved:
    _ct: Controller
    _get_team: Callable[..., Team]
    _get_position: Callable[..., Position]
    _get_id: Callable[..., int]
    _get_action_cooldown: Callable[..., int]
    _get_move_cooldown: Callable[..., int]
    _get_ammo_amount: Callable[..., int]
    _get_ammo_type: Callable[..., ResourceType | None]
    _get_vision_radius_sq: Callable[..., int]
    _get_hp: Callable[..., int]
    _get_max_hp: Callable[..., int]
    _get_entity_type: Callable[..., EntityType]
    _get_direction: Callable[..., Direction]
    _get_bridge_target: Callable[..., Position]
    _get_stored_resource: Callable[..., ResourceType | None]
    _get_stored_resource_id: Callable[..., int | None]
    _get_tile_env: Callable[..., Environment]
    _get_tile_building_id: Callable[..., int | None]
    _get_tile_builder_bot_id: Callable[..., int | None]
    _is_tile_empty: Callable[..., bool]
    _is_tile_passable: Callable[..., bool]
    _is_in_vision: Callable[..., bool]
    _get_nearby_tiles: Callable[..., list[Position]]
    _get_nearby_entities: Callable[..., list[int]]
    _get_nearby_buildings: Callable[..., list[int]]
    _get_nearby_units: Callable[..., list[int]]
    _get_map_width: Callable[..., int]
    _get_map_height: Callable[..., int]
    _get_current_round: Callable[..., int]
    _get_global_resources: Callable[..., tuple[int, int]]
    _get_scale_percent: Callable[..., float]
    _get_cpu_time_elapsed: Callable[..., int]
    _get_conveyor_cost: Callable[..., tuple[int, int]]
    _get_splitter_cost: Callable[..., tuple[int, int]]
    _get_bridge_cost: Callable[..., tuple[int, int]]
    _get_armoured_conveyor_cost: Callable[..., tuple[int, int]]
    _get_harvester_cost: Callable[..., tuple[int, int]]
    _get_road_cost: Callable[..., tuple[int, int]]
    _get_barrier_cost: Callable[..., tuple[int, int]]
    _get_gunner_cost: Callable[..., tuple[int, int]]
    _get_sentinel_cost: Callable[..., tuple[int, int]]
    _get_breach_cost: Callable[..., tuple[int, int]]
    _get_launcher_cost: Callable[..., tuple[int, int]]
    _get_foundry_cost: Callable[..., tuple[int, int]]
    _get_builder_bot_cost: Callable[..., tuple[int, int]]
    _get_unit_count: Callable[..., int]
    _move: Callable[..., None]
    _can_move: Callable[..., bool]
    _can_build_conveyor: Callable[..., bool]
    _can_build_splitter: Callable[..., bool]
    _can_build_bridge: Callable[..., bool]
    _can_build_armoured_conveyor: Callable[..., bool]
    _can_build_harvester: Callable[..., bool]
    _can_build_road: Callable[..., bool]
    _can_build_barrier: Callable[..., bool]
    _can_build_gunner: Callable[..., bool]
    _can_build_sentinel: Callable[..., bool]
    _can_build_breach: Callable[..., bool]
    _can_build_launcher: Callable[..., bool]
    _can_build_foundry: Callable[..., bool]
    _build_conveyor: Callable[..., int]
    _build_splitter: Callable[..., int]
    _build_bridge: Callable[..., int]
    _build_armoured_conveyor: Callable[..., int]
    _build_harvester: Callable[..., int]
    _build_road: Callable[..., int]
    _build_barrier: Callable[..., int]
    _build_gunner: Callable[..., int]
    _build_sentinel: Callable[..., int]
    _build_breach: Callable[..., int]
    _build_launcher: Callable[..., int]
    _build_foundry: Callable[..., int]
    _can_build: Callable[..., bool]
    _build: Callable[..., int]
    _heal: Callable[..., None]
    _can_heal: Callable[..., bool]
    _can_destroy: Callable[..., bool]
    _destroy: Callable[..., None]
    _self_destruct: Callable[..., None]
    _resign: Callable[..., None]
    _can_place_marker: Callable[..., bool]
    _place_marker: Callable[..., None]
    _get_marker_value: Callable[..., int]
    _can_fire: Callable[..., bool]
    _can_fire_from: Callable[..., bool]
    _fire: Callable[..., None]
    _can_rotate: Callable[..., bool]
    _rotate: Callable[..., None]
    _get_gunner_target: Callable[..., Position | None]
    _get_attackable_tiles: Callable[..., list[Position]]
    _get_attackable_tiles_from: Callable[..., list[Position]]
    _can_launch: Callable[..., bool]
    _launch: Callable[..., None]
    _convert: Callable[..., None]
    _spawn_builder: Callable[..., int]
    _can_spawn: Callable[..., bool]
    _draw_indicator_line: Callable[..., None]
    _draw_indicator_dot: Callable[..., None]

    def __init__(self, ct: Controller) -> None:
        self._ct = ct
        self._get_team = Controller.get_team
        self._get_position = Controller.get_position
        self._get_id = Controller.get_id
        self._get_action_cooldown = Controller.get_action_cooldown
        self._get_move_cooldown = Controller.get_move_cooldown
        self._get_ammo_amount = Controller.get_ammo_amount
        self._get_ammo_type = Controller.get_ammo_type
        self._get_vision_radius_sq = Controller.get_vision_radius_sq
        self._get_hp = Controller.get_hp
        self._get_max_hp = Controller.get_max_hp
        self._get_entity_type = Controller.get_entity_type
        self._get_direction = Controller.get_direction
        self._get_bridge_target = Controller.get_bridge_target
        self._get_stored_resource = Controller.get_stored_resource
        self._get_stored_resource_id = Controller.get_stored_resource_id
        self._get_tile_env = Controller.get_tile_env
        self._get_tile_building_id = Controller.get_tile_building_id
        self._get_tile_builder_bot_id = Controller.get_tile_builder_bot_id
        self._is_tile_empty = Controller.is_tile_empty
        self._is_tile_passable = Controller.is_tile_passable
        self._is_in_vision = Controller.is_in_vision
        self._get_nearby_tiles = Controller.get_nearby_tiles
        self._get_nearby_entities = Controller.get_nearby_entities
        self._get_nearby_buildings = Controller.get_nearby_buildings
        self._get_nearby_units = Controller.get_nearby_units
        self._get_map_width = Controller.get_map_width
        self._get_map_height = Controller.get_map_height
        self._get_current_round = Controller.get_current_round
        self._get_global_resources = Controller.get_global_resources
        self._get_scale_percent = Controller.get_scale_percent
        self._get_cpu_time_elapsed = Controller.get_cpu_time_elapsed
        self._get_conveyor_cost = Controller.get_conveyor_cost
        self._get_splitter_cost = Controller.get_splitter_cost
        self._get_bridge_cost = Controller.get_bridge_cost
        self._get_armoured_conveyor_cost = Controller.get_armoured_conveyor_cost
        self._get_harvester_cost = Controller.get_harvester_cost
        self._get_road_cost = Controller.get_road_cost
        self._get_barrier_cost = Controller.get_barrier_cost
        self._get_gunner_cost = Controller.get_gunner_cost
        self._get_sentinel_cost = Controller.get_sentinel_cost
        self._get_breach_cost = Controller.get_breach_cost
        self._get_launcher_cost = Controller.get_launcher_cost
        self._get_foundry_cost = Controller.get_foundry_cost
        self._get_builder_bot_cost = Controller.get_builder_bot_cost
        self._get_unit_count = Controller.get_unit_count
        self._move = Controller.move
        self._can_move = Controller.can_move
        self._can_build_conveyor = Controller.can_build_conveyor
        self._can_build_splitter = Controller.can_build_splitter
        self._can_build_bridge = Controller.can_build_bridge
        self._can_build_armoured_conveyor = Controller.can_build_armoured_conveyor
        self._can_build_harvester = Controller.can_build_harvester
        self._can_build_road = Controller.can_build_road
        self._can_build_barrier = Controller.can_build_barrier
        self._can_build_gunner = Controller.can_build_gunner
        self._can_build_sentinel = Controller.can_build_sentinel
        self._can_build_breach = Controller.can_build_breach
        self._can_build_launcher = Controller.can_build_launcher
        self._can_build_foundry = Controller.can_build_foundry
        self._build_conveyor = Controller.build_conveyor
        self._build_splitter = Controller.build_splitter
        self._build_bridge = Controller.build_bridge
        self._build_armoured_conveyor = Controller.build_armoured_conveyor
        self._build_harvester = Controller.build_harvester
        self._build_road = Controller.build_road
        self._build_barrier = Controller.build_barrier
        self._build_gunner = Controller.build_gunner
        self._build_sentinel = Controller.build_sentinel
        self._build_breach = Controller.build_breach
        self._build_launcher = Controller.build_launcher
        self._build_foundry = Controller.build_foundry
        self._can_build = Controller.can_build
        self._build = Controller.build
        self._heal = Controller.heal
        self._can_heal = Controller.can_heal
        self._can_destroy = Controller.can_destroy
        self._destroy = Controller.destroy
        self._self_destruct = Controller.self_destruct
        self._resign = Controller.resign
        self._can_place_marker = Controller.can_place_marker
        self._place_marker = Controller.place_marker
        self._get_marker_value = Controller.get_marker_value
        self._can_fire = Controller.can_fire
        self._can_fire_from = Controller.can_fire_from
        self._fire = Controller.fire
        self._can_rotate = Controller.can_rotate
        self._rotate = Controller.rotate
        self._get_gunner_target = Controller.get_gunner_target
        self._get_attackable_tiles = Controller.get_attackable_tiles
        self._get_attackable_tiles_from = Controller.get_attackable_tiles_from
        self._can_launch = Controller.can_launch
        self._launch = Controller.launch
        self._convert = Controller.convert
        self._spawn_builder = Controller.spawn_builder
        self._can_spawn = Controller.can_spawn
        self._draw_indicator_line = Controller.draw_indicator_line
        self._draw_indicator_dot = Controller.draw_indicator_dot

    def get_team(self: Saved, id: int | None = None) -> Team:
        return self._get_team(self._ct, id)

    def get_position(self: Saved, id: int | None = None) -> Position:
        return self._get_position(self._ct, id)

    def get_id(self: Saved) -> int:
        return self._get_id(self._ct)

    def get_action_cooldown(self: Saved) -> int:
        return self._get_action_cooldown(self._ct)

    def get_move_cooldown(self: Saved) -> int:
        return self._get_move_cooldown(self._ct)

    def get_ammo_amount(self: Saved) -> int:
        return self._get_ammo_amount(self._ct)

    def get_ammo_type(self: Saved) -> ResourceType | None:
        return self._get_ammo_type(self._ct)

    def get_vision_radius_sq(self: Saved, id: int | None = None) -> int:
        return self._get_vision_radius_sq(self._ct, id)

    def get_hp(self: Saved, id: int | None = None) -> int:
        return self._get_hp(self._ct, id)

    def get_max_hp(self: Saved, id: int | None = None) -> int:
        return self._get_max_hp(self._ct, id)

    def get_entity_type(self: Saved, id: int | None = None) -> EntityType:
        return self._get_entity_type(self._ct, id)

    def get_direction(self: Saved, id: int | None = None) -> Direction:
        return self._get_direction(self._ct, id)

    def get_bridge_target(self: Saved, id: int) -> Position:
        return self._get_bridge_target(self._ct, id)

    def get_stored_resource(self: Saved, id: int | None = None) -> ResourceType | None:
        return self._get_stored_resource(self._ct, id)

    def get_stored_resource_id(self: Saved, id: int | None = None) -> int | None:
        return self._get_stored_resource_id(self._ct, id)

    def get_tile_env(self: Saved, pos: Position) -> Environment:
        return self._get_tile_env(self._ct, pos)

    def get_tile_building_id(self: Saved, pos: Position) -> int | None:
        return self._get_tile_building_id(self._ct, pos)

    def get_tile_builder_bot_id(self: Saved, pos: Position) -> int | None:
        return self._get_tile_builder_bot_id(self._ct, pos)

    def is_tile_empty(self: Saved, pos: Position) -> bool:
        return self._is_tile_empty(self._ct, pos)

    def is_tile_passable(self: Saved, pos: Position) -> bool:
        return self._is_tile_passable(self._ct, pos)

    def is_in_vision(self: Saved, pos: Position) -> bool:
        return self._is_in_vision(self._ct, pos)

    def get_nearby_tiles(self: Saved, dist_sq: int | None = None) -> list[Position]:
        return self._get_nearby_tiles(self._ct, dist_sq)

    def get_nearby_entities(self: Saved, dist_sq: int | None = None) -> list[int]:
        return self._get_nearby_entities(self._ct, dist_sq)

    def get_nearby_buildings(self: Saved, dist_sq: int | None = None) -> list[int]:
        return self._get_nearby_buildings(self._ct, dist_sq)

    def get_nearby_units(self: Saved, dist_sq: int | None = None) -> list[int]:
        return self._get_nearby_units(self._ct, dist_sq)

    def get_map_width(self: Saved) -> int:
        return self._get_map_width(self._ct)

    def get_map_height(self: Saved) -> int:
        return self._get_map_height(self._ct)

    def get_current_round(self: Saved) -> int:
        return self._get_current_round(self._ct)

    def get_global_resources(self: Saved) -> tuple[int, int]:
        return self._get_global_resources(self._ct)

    def get_scale_percent(self: Saved) -> float:
        return self._get_scale_percent(self._ct)

    def get_cpu_time_elapsed(self: Saved) -> int:
        return self._get_cpu_time_elapsed(self._ct)

    def get_conveyor_cost(self: Saved) -> tuple[int, int]:
        return self._get_conveyor_cost(self._ct)

    def get_splitter_cost(self: Saved) -> tuple[int, int]:
        return self._get_splitter_cost(self._ct)

    def get_bridge_cost(self: Saved) -> tuple[int, int]:
        return self._get_bridge_cost(self._ct)

    def get_armoured_conveyor_cost(self: Saved) -> tuple[int, int]:
        return self._get_armoured_conveyor_cost(self._ct)

    def get_harvester_cost(self: Saved) -> tuple[int, int]:
        return self._get_harvester_cost(self._ct)

    def get_road_cost(self: Saved) -> tuple[int, int]:
        return self._get_road_cost(self._ct)

    def get_barrier_cost(self: Saved) -> tuple[int, int]:
        return self._get_barrier_cost(self._ct)

    def get_gunner_cost(self: Saved) -> tuple[int, int]:
        return self._get_gunner_cost(self._ct)

    def get_sentinel_cost(self: Saved) -> tuple[int, int]:
        return self._get_sentinel_cost(self._ct)

    def get_breach_cost(self: Saved) -> tuple[int, int]:
        return self._get_breach_cost(self._ct)

    def get_launcher_cost(self: Saved) -> tuple[int, int]:
        return self._get_launcher_cost(self._ct)

    def get_foundry_cost(self: Saved) -> tuple[int, int]:
        return self._get_foundry_cost(self._ct)

    def get_builder_bot_cost(self: Saved) -> tuple[int, int]:
        return self._get_builder_bot_cost(self._ct)

    def get_unit_count(self: Saved) -> int:
        return self._get_unit_count(self._ct)

    def move(self: Saved, direction: Direction) -> None:
        return self._move(self._ct, direction)

    def can_move(self: Saved, direction: Direction) -> bool:
        return self._can_move(self._ct, direction)

    def can_build_conveyor(
        self: Saved, position: Position, direction: Direction
    ) -> bool:
        return self._can_build_conveyor(self._ct, position, direction)

    def can_build_splitter(
        self: Saved, position: Position, direction: Direction
    ) -> bool:
        return self._can_build_splitter(self._ct, position, direction)

    def can_build_bridge(self: Saved, position: Position, target: Position) -> bool:
        return self._can_build_bridge(self._ct, position, target)

    def can_build_armoured_conveyor(
        self: Saved, position: Position, direction: Direction
    ) -> bool:
        return self._can_build_armoured_conveyor(self._ct, position, direction)

    def can_build_harvester(self: Saved, position: Position) -> bool:
        return self._can_build_harvester(self._ct, position)

    def can_build_road(self: Saved, position: Position) -> bool:
        return self._can_build_road(self._ct, position)

    def can_build_barrier(self: Saved, position: Position) -> bool:
        return self._can_build_barrier(self._ct, position)

    def can_build_gunner(self: Saved, position: Position, direction: Direction) -> bool:
        return self._can_build_gunner(self._ct, position, direction)

    def can_build_sentinel(
        self: Saved, position: Position, direction: Direction
    ) -> bool:
        return self._can_build_sentinel(self._ct, position, direction)

    def can_build_breach(self: Saved, position: Position, direction: Direction) -> bool:
        return self._can_build_breach(self._ct, position, direction)

    def can_build_launcher(self: Saved, position: Position) -> bool:
        return self._can_build_launcher(self._ct, position)

    def can_build_foundry(self: Saved, position: Position) -> bool:
        return self._can_build_foundry(self._ct, position)

    def build_conveyor(self: Saved, position: Position, direction: Direction) -> int:
        return self._build_conveyor(self._ct, position, direction)

    def build_splitter(self: Saved, position: Position, direction: Direction) -> int:
        return self._build_splitter(self._ct, position, direction)

    def build_bridge(self: Saved, position: Position, target: Position) -> int:
        return self._build_bridge(self._ct, position, target)

    def build_armoured_conveyor(
        self: Saved, position: Position, direction: Direction
    ) -> int:
        return self._build_armoured_conveyor(self._ct, position, direction)

    def build_harvester(self: Saved, position: Position) -> int:
        return self._build_harvester(self._ct, position)

    def build_road(self: Saved, position: Position) -> int:
        return self._build_road(self._ct, position)

    def build_barrier(self: Saved, position: Position) -> int:
        return self._build_barrier(self._ct, position)

    def build_gunner(self: Saved, position: Position, direction: Direction) -> int:
        return self._build_gunner(self._ct, position, direction)

    def build_sentinel(self: Saved, position: Position, direction: Direction) -> int:
        return self._build_sentinel(self._ct, position, direction)

    def build_breach(self: Saved, position: Position, direction: Direction) -> int:
        return self._build_breach(self._ct, position, direction)

    def build_launcher(self: Saved, position: Position) -> int:
        return self._build_launcher(self._ct, position)

    def build_foundry(self: Saved, position: Position) -> int:
        return self._build_foundry(self._ct, position)

    def can_build(
        self: Saved,
        entity_type: EntityType,
        position: Position,
        extra: Direction | Position | None = None,
    ) -> bool:
        return self._can_build(self._ct, entity_type, position, extra)

    def build(
        self: Saved,
        entity_type: EntityType,
        position: Position,
        extra: Direction | Position | None = None,
    ) -> int:
        return self._build(self._ct, entity_type, position, extra)

    def heal(self: Saved, position: Position) -> None:
        return self._heal(self._ct, position)

    def can_heal(self: Saved, position: Position) -> bool:
        return self._can_heal(self._ct, position)

    def can_destroy(self: Saved, building_pos: Position) -> bool:
        return self._can_destroy(self._ct, building_pos)

    def destroy(self: Saved, building_pos: Position) -> None:
        return self._destroy(self._ct, building_pos)

    def self_destruct(self: Saved) -> None:
        return self._self_destruct(self._ct)

    def resign(self: Saved, message: str | None = None) -> None:
        return self._resign(self._ct, message)

    def can_place_marker(self: Saved, position: Position) -> bool:
        return self._can_place_marker(self._ct, position)

    def place_marker(self: Saved, position: Position, value: int) -> None:
        return self._place_marker(self._ct, position, value)

    def get_marker_value(self: Saved, id: int) -> int:
        return self._get_marker_value(self._ct, id)

    def can_fire(self: Saved, target: Position) -> bool:
        return self._can_fire(self._ct, target)

    def can_fire_from(
        self: Saved,
        position: Position,
        direction: Direction,
        turret_type: EntityType,
        target: Position,
    ) -> bool:
        return self._can_fire_from(self._ct, position, direction, turret_type, target)

    def fire(self: Saved, target: Position) -> None:
        return self._fire(self._ct, target)

    def can_rotate(self: Saved, direction: Direction) -> bool:
        return self._can_rotate(self._ct, direction)

    def rotate(self: Saved, direction: Direction) -> None:
        return self._rotate(self._ct, direction)

    def get_gunner_target(self: Saved) -> Position | None:
        return self._get_gunner_target(self._ct)

    def get_attackable_tiles(self: Saved) -> list[Position]:
        return self._get_attackable_tiles(self._ct)

    def get_attackable_tiles_from(
        self: Saved, position: Position, direction: Direction, turret_type: EntityType
    ) -> list[Position]:
        return self._get_attackable_tiles_from(
            self._ct, position, direction, turret_type
        )

    def can_launch(self: Saved, bot_pos: Position, target: Position) -> bool:
        return self._can_launch(self._ct, bot_pos, target)

    def launch(self: Saved, bot_pos: Position, target: Position) -> None:
        return self._launch(self._ct, bot_pos, target)

    def convert(self: Saved, amount: int) -> None:
        return self._convert(self._ct, amount)

    def spawn_builder(self: Saved, position: Position) -> int:
        return self._spawn_builder(self._ct, position)

    def can_spawn(self: Saved, position: Position) -> bool:
        return self._can_spawn(self._ct, position)

    def draw_indicator_line(
        self: Saved, pos_a: Position, pos_b: Position, r: int, g: int, b: int
    ) -> None:
        return self._draw_indicator_line(self._ct, pos_a, pos_b, r, g, b)

    def draw_indicator_dot(self: Saved, pos: Position, r: int, g: int, b: int) -> None:
        return self._draw_indicator_dot(self._ct, pos, r, g, b)


def save(ct: Controller) -> Saved:
    return Saved(ct)
