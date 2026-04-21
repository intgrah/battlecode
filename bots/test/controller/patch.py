# ruff: noqa: A002
from cambc import (
    Controller,
    Direction,
    EntityType,
    Environment,
    Position,
    ResourceType,
    Team,
)
from save import Saved


def patch(saved: Saved) -> None:
    def get_team(self: Controller, id: int | None = None) -> Team:
        return saved._get_team(self, id)

    def get_position(self: Controller, id: int | None = None) -> Position:
        return saved._get_position(self, id)

    def get_id(self: Controller) -> int:
        return saved._get_id(self)

    def get_action_cooldown(self: Controller) -> int:
        return saved._get_action_cooldown(self)

    def get_move_cooldown(self: Controller) -> int:
        return saved._get_move_cooldown(self)

    def get_ammo_amount(self: Controller) -> int:
        return saved._get_ammo_amount(self)

    def get_ammo_type(self: Controller) -> ResourceType | None:
        return saved._get_ammo_type(self)

    def get_vision_radius_sq(self: Controller, id: int | None = None) -> int:
        return saved._get_vision_radius_sq(self, id)

    def get_hp(self: Controller, id: int | None = None) -> int:
        return saved._get_hp(self, id)

    def get_max_hp(self: Controller, id: int | None = None) -> int:
        return saved._get_max_hp(self, id)

    def get_entity_type(self: Controller, id: int | None = None) -> EntityType:
        return saved._get_entity_type(self, id)

    def get_direction(self: Controller, id: int | None = None) -> Direction:
        return saved._get_direction(self, id)

    def get_bridge_target(self: Controller, id: int) -> Position:
        return saved._get_bridge_target(self, id)

    def get_stored_resource(
        self: Controller, id: int | None = None
    ) -> ResourceType | None:
        return saved._get_stored_resource(self, id)

    def get_stored_resource_id(self: Controller, id: int | None = None) -> int | None:
        return saved._get_stored_resource_id(self, id)

    def get_tile_env(self: Controller, pos: Position) -> Environment:
        return saved._get_tile_env(self, pos)

    def get_tile_building_id(self: Controller, pos: Position) -> int | None:
        return saved._get_tile_building_id(self, pos)

    def get_tile_builder_bot_id(self: Controller, pos: Position) -> int | None:
        return saved._get_tile_builder_bot_id(self, pos)

    def is_tile_empty(self: Controller, pos: Position) -> bool:
        return saved._is_tile_empty(self, pos)

    def is_tile_passable(self: Controller, pos: Position) -> bool:
        return saved._is_tile_passable(self, pos)

    def is_in_vision(self: Controller, pos: Position) -> bool:
        return saved._is_in_vision(self, pos)

    def get_nearby_tiles(
        self: Controller, dist_sq: int | None = None
    ) -> list[Position]:
        return saved._get_nearby_tiles(self, dist_sq)

    def get_nearby_entities(self: Controller, dist_sq: int | None = None) -> list[int]:
        return saved._get_nearby_entities(self, dist_sq)

    def get_nearby_buildings(self: Controller, dist_sq: int | None = None) -> list[int]:
        return saved._get_nearby_buildings(self, dist_sq)

    def get_nearby_units(self: Controller, dist_sq: int | None = None) -> list[int]:
        return saved._get_nearby_units(self, dist_sq)

    def get_map_width(self: Controller) -> int:
        return saved._get_map_width(self)

    def get_map_height(self: Controller) -> int:
        return saved._get_map_height(self)

    def get_current_round(self: Controller) -> int:
        return saved._get_current_round(self)

    def get_global_resources(self: Controller) -> tuple[int, int]:
        return saved._get_global_resources(self)

    def get_scale_percent(self: Controller) -> float:
        return saved._get_scale_percent(self)

    def get_cpu_time_elapsed(self: Controller) -> int:
        return saved._get_cpu_time_elapsed(self)

    def get_conveyor_cost(self: Controller) -> tuple[int, int]:
        return saved._get_conveyor_cost(self)

    def get_splitter_cost(self: Controller) -> tuple[int, int]:
        return saved._get_splitter_cost(self)

    def get_bridge_cost(self: Controller) -> tuple[int, int]:
        return saved._get_bridge_cost(self)

    def get_armoured_conveyor_cost(self: Controller) -> tuple[int, int]:
        return saved._get_armoured_conveyor_cost(self)

    def get_harvester_cost(self: Controller) -> tuple[int, int]:
        return saved._get_harvester_cost(self)

    def get_road_cost(self: Controller) -> tuple[int, int]:
        return saved._get_road_cost(self)

    def get_barrier_cost(self: Controller) -> tuple[int, int]:
        return saved._get_barrier_cost(self)

    def get_gunner_cost(self: Controller) -> tuple[int, int]:
        return saved._get_gunner_cost(self)

    def get_sentinel_cost(self: Controller) -> tuple[int, int]:
        return saved._get_sentinel_cost(self)

    def get_breach_cost(self: Controller) -> tuple[int, int]:
        return saved._get_breach_cost(self)

    def get_launcher_cost(self: Controller) -> tuple[int, int]:
        return saved._get_launcher_cost(self)

    def get_foundry_cost(self: Controller) -> tuple[int, int]:
        return saved._get_foundry_cost(self)

    def get_builder_bot_cost(self: Controller) -> tuple[int, int]:
        return saved._get_builder_bot_cost(self)

    def get_unit_count(self: Controller) -> int:
        return saved._get_unit_count(self)

    def move(self: Controller, direction: Direction) -> None:
        return saved._move(self, direction)

    def can_move(self: Controller, direction: Direction) -> bool:
        return saved._can_move(self, direction)

    def can_build_conveyor(
        self: Controller, position: Position, direction: Direction
    ) -> bool:
        return saved._can_build_conveyor(self, position, direction)

    def can_build_splitter(
        self: Controller, position: Position, direction: Direction
    ) -> bool:
        return saved._can_build_splitter(self, position, direction)

    def can_build_bridge(
        self: Controller, position: Position, target: Position
    ) -> bool:
        return saved._can_build_bridge(self, position, target)

    def can_build_armoured_conveyor(
        self: Controller, position: Position, direction: Direction
    ) -> bool:
        return saved._can_build_armoured_conveyor(self, position, direction)

    def can_build_harvester(self: Controller, position: Position) -> bool:
        return saved._can_build_harvester(self, position)

    def can_build_road(self: Controller, position: Position) -> bool:
        return saved._can_build_road(self, position)

    def can_build_barrier(self: Controller, position: Position) -> bool:
        return saved._can_build_barrier(self, position)

    def can_build_gunner(
        self: Controller, position: Position, direction: Direction
    ) -> bool:
        return saved._can_build_gunner(self, position, direction)

    def can_build_sentinel(
        self: Controller, position: Position, direction: Direction
    ) -> bool:
        return saved._can_build_sentinel(self, position, direction)

    def can_build_breach(
        self: Controller, position: Position, direction: Direction
    ) -> bool:
        return saved._can_build_breach(self, position, direction)

    def can_build_launcher(self: Controller, position: Position) -> bool:
        return saved._can_build_launcher(self, position)

    def can_build_foundry(self: Controller, position: Position) -> bool:
        return saved._can_build_foundry(self, position)

    def build_conveyor(
        self: Controller, position: Position, direction: Direction
    ) -> int:
        return saved._build_conveyor(self, position, direction)

    def build_splitter(
        self: Controller, position: Position, direction: Direction
    ) -> int:
        return saved._build_splitter(self, position, direction)

    def build_bridge(self: Controller, position: Position, target: Position) -> int:
        return saved._build_bridge(self, position, target)

    def build_armoured_conveyor(
        self: Controller, position: Position, direction: Direction
    ) -> int:
        return saved._build_armoured_conveyor(self, position, direction)

    def build_harvester(self: Controller, position: Position) -> int:
        return saved._build_harvester(self, position)

    def build_road(self: Controller, position: Position) -> int:
        return saved._build_road(self, position)

    def build_barrier(self: Controller, position: Position) -> int:
        return saved._build_barrier(self, position)

    def build_gunner(self: Controller, position: Position, direction: Direction) -> int:
        return saved._build_gunner(self, position, direction)

    def build_sentinel(
        self: Controller, position: Position, direction: Direction
    ) -> int:
        return saved._build_sentinel(self, position, direction)

    def build_breach(self: Controller, position: Position, direction: Direction) -> int:
        return saved._build_breach(self, position, direction)

    def build_launcher(self: Controller, position: Position) -> int:
        return saved._build_launcher(self, position)

    def build_foundry(self: Controller, position: Position) -> int:
        return saved._build_foundry(self, position)

    def can_build(
        self: Controller,
        entity_type: EntityType,
        position: Position,
        extra: Direction | Position | None = None,
    ) -> bool:
        return saved._can_build(self, entity_type, position, extra)

    def build(
        self: Controller,
        entity_type: EntityType,
        position: Position,
        extra: Direction | Position | None = None,
    ) -> int:
        return saved._build(self, entity_type, position, extra)

    def heal(self: Controller, position: Position) -> None:
        return saved._heal(self, position)

    def can_heal(self: Controller, position: Position) -> bool:
        return saved._can_heal(self, position)

    def can_destroy(self: Controller, building_pos: Position) -> bool:
        return saved._can_destroy(self, building_pos)

    def destroy(self: Controller, building_pos: Position) -> None:
        return saved._destroy(self, building_pos)

    def self_destruct(self: Controller) -> None:
        return saved._self_destruct(self)

    def resign(self: Controller, message: str | None = None) -> None:
        return saved._resign(self, message)

    def can_place_marker(self: Controller, position: Position) -> bool:
        return saved._can_place_marker(self, position)

    def place_marker(self: Controller, position: Position, value: int) -> None:
        return saved._place_marker(self, position, value)

    def get_marker_value(self: Controller, id: int) -> int:
        return saved._get_marker_value(self, id)

    def can_fire(self: Controller, target: Position) -> bool:
        return saved._can_fire(self, target)

    def can_fire_from(
        self: Controller,
        position: Position,
        direction: Direction,
        turret_type: EntityType,
        target: Position,
    ) -> bool:
        return saved._can_fire_from(self, position, direction, turret_type, target)

    def fire(self: Controller, target: Position) -> None:
        return saved._fire(self, target)

    def can_rotate(self: Controller, direction: Direction) -> bool:
        return saved._can_rotate(self, direction)

    def rotate(self: Controller, direction: Direction) -> None:
        return saved._rotate(self, direction)

    def get_gunner_target(self: Controller) -> Position | None:
        return saved._get_gunner_target(self)

    def get_attackable_tiles(self: Controller) -> list[Position]:
        return saved._get_attackable_tiles(self)

    def get_attackable_tiles_from(
        self: Controller,
        position: Position,
        direction: Direction,
        turret_type: EntityType,
    ) -> list[Position]:
        return saved._get_attackable_tiles_from(self, position, direction, turret_type)

    def can_launch(self: Controller, bot_pos: Position, target: Position) -> bool:
        return saved._can_launch(self, bot_pos, target)

    def launch(self: Controller, bot_pos: Position, target: Position) -> None:
        return saved._launch(self, bot_pos, target)

    def convert(self: Controller, amount: int) -> None:
        return saved._convert(self, amount)

    def spawn_builder(self: Controller, position: Position) -> int:
        return saved._spawn_builder(self, position)

    def can_spawn(self: Controller, position: Position) -> bool:
        return saved._can_spawn(self, position)

    def draw_indicator_line(
        self: Controller, pos_a: Position, pos_b: Position, r: int, g: int, b: int
    ) -> None:
        return saved._draw_indicator_line(self, pos_a, pos_b, r, g, b)

    def draw_indicator_dot(
        self: Controller, pos: Position, r: int, g: int, b: int
    ) -> None:
        return saved._draw_indicator_dot(self, pos, r, g, b)

    Controller.get_team = get_team
    Controller.get_position = get_position
    Controller.get_id = get_id
    Controller.get_action_cooldown = get_action_cooldown
    Controller.get_move_cooldown = get_move_cooldown
    Controller.get_ammo_amount = get_ammo_amount
    Controller.get_ammo_type = get_ammo_type
    Controller.get_vision_radius_sq = get_vision_radius_sq
    Controller.get_hp = get_hp
    Controller.get_max_hp = get_max_hp
    Controller.get_entity_type = get_entity_type
    Controller.get_direction = get_direction
    Controller.get_bridge_target = get_bridge_target
    Controller.get_stored_resource = get_stored_resource
    Controller.get_stored_resource_id = get_stored_resource_id
    Controller.get_tile_env = get_tile_env
    Controller.get_tile_building_id = get_tile_building_id
    Controller.get_tile_builder_bot_id = get_tile_builder_bot_id
    Controller.is_tile_empty = is_tile_empty
    Controller.is_tile_passable = is_tile_passable
    Controller.is_in_vision = is_in_vision
    Controller.get_nearby_tiles = get_nearby_tiles
    Controller.get_nearby_entities = get_nearby_entities
    Controller.get_nearby_buildings = get_nearby_buildings
    Controller.get_nearby_units = get_nearby_units
    Controller.get_map_width = get_map_width
    Controller.get_map_height = get_map_height
    Controller.get_current_round = get_current_round
    Controller.get_global_resources = get_global_resources
    Controller.get_scale_percent = get_scale_percent
    Controller.get_cpu_time_elapsed = get_cpu_time_elapsed
    Controller.get_conveyor_cost = get_conveyor_cost
    Controller.get_splitter_cost = get_splitter_cost
    Controller.get_bridge_cost = get_bridge_cost
    Controller.get_armoured_conveyor_cost = get_armoured_conveyor_cost
    Controller.get_harvester_cost = get_harvester_cost
    Controller.get_road_cost = get_road_cost
    Controller.get_barrier_cost = get_barrier_cost
    Controller.get_gunner_cost = get_gunner_cost
    Controller.get_sentinel_cost = get_sentinel_cost
    Controller.get_breach_cost = get_breach_cost
    Controller.get_launcher_cost = get_launcher_cost
    Controller.get_foundry_cost = get_foundry_cost
    Controller.get_builder_bot_cost = get_builder_bot_cost
    Controller.get_unit_count = get_unit_count
    Controller.move = move
    Controller.can_move = can_move
    Controller.can_build_conveyor = can_build_conveyor
    Controller.can_build_splitter = can_build_splitter
    Controller.can_build_bridge = can_build_bridge
    Controller.can_build_armoured_conveyor = can_build_armoured_conveyor
    Controller.can_build_harvester = can_build_harvester
    Controller.can_build_road = can_build_road
    Controller.can_build_barrier = can_build_barrier
    Controller.can_build_gunner = can_build_gunner
    Controller.can_build_sentinel = can_build_sentinel
    Controller.can_build_breach = can_build_breach
    Controller.can_build_launcher = can_build_launcher
    Controller.can_build_foundry = can_build_foundry
    Controller.build_conveyor = build_conveyor
    Controller.build_splitter = build_splitter
    Controller.build_bridge = build_bridge
    Controller.build_armoured_conveyor = build_armoured_conveyor
    Controller.build_harvester = build_harvester
    Controller.build_road = build_road
    Controller.build_barrier = build_barrier
    Controller.build_gunner = build_gunner
    Controller.build_sentinel = build_sentinel
    Controller.build_breach = build_breach
    Controller.build_launcher = build_launcher
    Controller.build_foundry = build_foundry
    Controller.can_build = can_build
    Controller.build = build
    Controller.heal = heal
    Controller.can_heal = can_heal
    Controller.can_destroy = can_destroy
    Controller.destroy = destroy
    Controller.self_destruct = self_destruct
    Controller.resign = resign
    Controller.can_place_marker = can_place_marker
    Controller.place_marker = place_marker
    Controller.get_marker_value = get_marker_value
    Controller.can_fire = can_fire
    Controller.can_fire_from = can_fire_from
    Controller.fire = fire
    Controller.can_rotate = can_rotate
    Controller.rotate = rotate
    Controller.get_gunner_target = get_gunner_target
    Controller.get_attackable_tiles = get_attackable_tiles
    Controller.get_attackable_tiles_from = get_attackable_tiles_from
    Controller.can_launch = can_launch
    Controller.launch = launch
    Controller.convert = convert
    Controller.spawn_builder = spawn_builder
    Controller.can_spawn = can_spawn
    Controller.draw_indicator_line = draw_indicator_line
    Controller.draw_indicator_dot = draw_indicator_dot
