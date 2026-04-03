"""Common types for the Titan game."""

from __future__ import annotations

from enum import Enum
from typing import NamedTuple


class GameError(Exception):
    """Raised when a player issues an invalid action."""

    __slots__ = ()


class Team(Enum):
    __slots__ = ()

    A = "a"
    B = "b"


class ResourceType(Enum):
    __slots__ = ()

    TITANIUM = "titanium"
    RAW_AXIONITE = "raw_axionite"
    REFINED_AXIONITE = "refined_axionite"


class EntityType(Enum):
    __slots__ = ()

    BUILDER_BOT = "builder_bot"
    CORE = "core"
    GUNNER = "gunner"
    SENTINEL = "sentinel"
    BREACH = "breach"
    LAUNCHER = "launcher"
    CONVEYOR = "conveyor"
    SPLITTER = "splitter"
    ARMOURED_CONVEYOR = "armoured_conveyor"
    BRIDGE = "bridge"
    HARVESTER = "harvester"
    FOUNDRY = "foundry"
    ROAD = "road"
    BARRIER = "barrier"
    MARKER = "marker"


class GameConstants:
    __slots__ = ()

    MAX_TURNS = 2000
    STACK_SIZE = 10
    STARTING_TITANIUM = 1000
    STARTING_AXIONITE = 0

    ACTION_RADIUS_SQ = 2
    CORE_SPAWNING_RADIUS_SQ = 2
    CORE_ACTION_RADIUS_SQ = 8

    BRIDGE_TARGET_RADIUS_SQ = 9

    CORE_VISION_RADIUS_SQ = 36
    BUILDER_BOT_VISION_RADIUS_SQ = 20
    GUNNER_VISION_RADIUS_SQ = 13
    SENTINEL_VISION_RADIUS_SQ = 32
    BREACH_VISION_RADIUS_SQ = 10
    LAUNCHER_VISION_RADIUS_SQ = 26

    CONVEYOR_BASE_COST = (3, 0)
    SPLITTER_BASE_COST = (6, 0)
    BRIDGE_BASE_COST = (10, 0)
    ARMOURED_CONVEYOR_BASE_COST = (10, 5)
    HARVESTER_BASE_COST = (80, 0)
    ROAD_BASE_COST = (1, 0)
    BARRIER_BASE_COST = (3, 0)
    GUNNER_BASE_COST = (10, 0)
    SENTINEL_BASE_COST = (15, 0)
    BREACH_BASE_COST = (30, 10)
    LAUNCHER_BASE_COST = (20, 0)
    FOUNDRY_BASE_COST = (120, 0)
    BUILDER_BOT_BASE_COST = (10, 0)

    CONVEYOR_MAX_HP = 20
    SPLITTER_MAX_HP = 20
    BRIDGE_MAX_HP = 20
    ARMOURED_CONVEYOR_MAX_HP = 50
    HARVESTER_MAX_HP = 30
    ROAD_MAX_HP = 10
    BARRIER_MAX_HP = 30
    FOUNDRY_MAX_HP = 50
    MARKER_MAX_HP = 1

    BUILDER_BOT_MAX_HP = 30
    CORE_MAX_HP = 500
    GUNNER_MAX_HP = 40
    SENTINEL_MAX_HP = 30
    BREACH_MAX_HP = 60
    LAUNCHER_MAX_HP = 30

    BUILDER_BOT_SELF_DESTRUCT_DAMAGE = 20
    HEAL_AMOUNT = 10

    GUNNER_DAMAGE = 10
    GUNNER_FIRE_COOLDOWN = 1
    GUNNER_AMMO_COST = 2

    SENTINEL_DAMAGE = 20
    SENTINEL_FIRE_COOLDOWN = 4
    SENTINEL_AMMO_COST = 10

    BREACH_DAMAGE = 40
    BREACH_SPLASH_DAMAGE = 20
    BREACH_FIRE_COOLDOWN = 1
    BREACH_AMMO_COST = 5
    BREACH_ATTACK_RADIUS_SQ = 5

    LAUNCHER_FIRE_COOLDOWN = 1



class Environment(Enum):
    __slots__ = ()

    EMPTY = "empty"
    WALL = "wall"
    ORE_TITANIUM = "ore_titanium"
    ORE_AXIONITE = "ore_axionite"


class Direction(Enum):
    __slots__ = ()

    NORTH = "north"
    NORTHEAST = "northeast"
    EAST = "east"
    SOUTHEAST = "southeast"
    SOUTH = "south"
    SOUTHWEST = "southwest"
    WEST = "west"
    NORTHWEST = "northwest"
    CENTRE = "centre"

    def delta(self) -> tuple[int, int]:
        """Return the (dx, dy) step for this direction."""
        return {
            Direction.NORTH: (0, -1),
            Direction.NORTHEAST: (1, -1),
            Direction.EAST: (1, 0),
            Direction.SOUTHEAST: (1, 1),
            Direction.SOUTH: (0, 1),
            Direction.SOUTHWEST: (-1, 1),
            Direction.WEST: (-1, 0),
            Direction.NORTHWEST: (-1, -1),
            Direction.CENTRE: (0, 0),
        }[self]

    def rotate_left(self) -> Direction:
        """Return the direction rotated 45 degrees counterclockwise."""
        return {
            Direction.NORTH: Direction.NORTHWEST,
            Direction.NORTHEAST: Direction.NORTH,
            Direction.EAST: Direction.NORTHEAST,
            Direction.SOUTHEAST: Direction.EAST,
            Direction.SOUTH: Direction.SOUTHEAST,
            Direction.SOUTHWEST: Direction.SOUTH,
            Direction.WEST: Direction.SOUTHWEST,
            Direction.NORTHWEST: Direction.WEST,
            Direction.CENTRE: Direction.CENTRE,
        }[self]

    def rotate_right(self) -> Direction:
        """Return the direction rotated 45 degrees clockwise."""
        return {
            Direction.NORTH: Direction.NORTHEAST,
            Direction.NORTHEAST: Direction.EAST,
            Direction.EAST: Direction.SOUTHEAST,
            Direction.SOUTHEAST: Direction.SOUTH,
            Direction.SOUTH: Direction.SOUTHWEST,
            Direction.SOUTHWEST: Direction.WEST,
            Direction.WEST: Direction.NORTHWEST,
            Direction.NORTHWEST: Direction.NORTH,
            Direction.CENTRE: Direction.CENTRE,
        }[self]

    def opposite(self) -> Direction:
        """Return the opposite direction (180 degrees)."""
        return {
            Direction.NORTH: Direction.SOUTH,
            Direction.NORTHEAST: Direction.SOUTHWEST,
            Direction.EAST: Direction.WEST,
            Direction.SOUTHEAST: Direction.NORTHWEST,
            Direction.SOUTH: Direction.NORTH,
            Direction.SOUTHWEST: Direction.NORTHEAST,
            Direction.WEST: Direction.EAST,
            Direction.NORTHWEST: Direction.SOUTHEAST,
            Direction.CENTRE: Direction.CENTRE,
        }[self]


class Position(NamedTuple):
    x: int
    y: int

    def add(self, d: Direction) -> Position:
        """Return a new position offset by the direction delta."""
        dx, dy = d.delta()
        return Position(self.x + dx, self.y + dy)

    def distance_squared(self, other: Position) -> int:
        """Return squared distance to another position."""
        dx = self.x - other.x
        dy = self.y - other.y
        return dx * dx + dy * dy

    def direction_to(self, other: Position) -> Direction:
        """Return the closest 45-degree Direction approximation toward other."""
        dx = other.x - self.x
        dy = other.y - self.y
        if dx == 0 and dy == 0:
            return Direction.CENTRE
        # atan2 gives angle in radians; map to one of 8 compass directions.
        import math
        # Use y-up convention for direction mapping: north is decreasing y.
        angle = math.atan2(-dy, dx)  # radians, x-east / y-north convention
        # Snap to nearest 45-degree sector (each sector is pi/4 wide).
        # Sectors: E=0, NE=1, N=2, NW=3, W=4, SW=5, S=6, SE=7
        sector = int((angle + 2 * math.pi + math.pi / 8) / (math.pi / 4)) % 8
        return [
            Direction.EAST,
            Direction.NORTHEAST,
            Direction.NORTH,
            Direction.NORTHWEST,
            Direction.WEST,
            Direction.SOUTHWEST,
            Direction.SOUTH,
            Direction.SOUTHEAST,
        ][sector]


# Stub for type-checking only. The real Controller is injected from Rust at runtime.
# Keep in sync with engine/rust/src/bindings/controller.rs.

class Controller:
    # --- Info ---

    def get_team(self, id: int | None = None) -> Team:
        """Return the team of the entity with the given id, or this unit if omitted."""
        ...

    def get_position(self, id: int | None = None) -> Position:
        """Return the position of the entity with the given id, or this unit if omitted."""
        ...

    def get_id(self) -> int:
        """Return this unit's entity id."""
        ...

    def get_action_cooldown(self) -> int:
        """Return this unit's current action cooldown. Actions require cooldown == 0."""
        ...

    def get_move_cooldown(self) -> int:
        """Return this unit's current move cooldown. Movement requires cooldown == 0."""
        ...

    def get_ammo_amount(self) -> int:
        """Return the amount of ammo this turret currently holds."""
        ...

    def get_ammo_type(self) -> ResourceType | None:
        """Return the resource type loaded as ammo, or None if empty."""
        ...

    def get_vision_radius_sq(self, id: int | None = None) -> int:
        """Return the vision radius squared of the given unit, or this unit if omitted."""
        ...

    def get_hp(self, id: int | None = None) -> int:
        """Return the current HP of the entity with the given id, or this unit if omitted."""
        ...

    def get_max_hp(self, id: int | None = None) -> int:
        """Return the max HP of the entity with the given id, or this unit if omitted."""
        ...

    def get_entity_type(self, id: int | None = None) -> EntityType:
        """Return the EntityType of the entity with the given id, or this unit if omitted."""
        ...

    def get_direction(self, id: int | None = None) -> Direction:
        """Return the facing direction of a conveyor, splitter, armoured conveyor, or turret.
        Raises GameError if the entity has no direction."""
        ...

    def get_bridge_target(self, id: int) -> Position:
        """Return the output target position of a bridge. Raises GameError if not a bridge."""
        ...

    def get_stored_resource(self, id: int | None = None) -> ResourceType | None:
        """Return the resource stored in a conveyor, splitter, armoured conveyor, bridge, or foundry.
        Returns None if empty. Raises GameError if the entity has no storage."""
        ...

    def get_tile_env(self, pos: Position) -> Environment:
        """Return the environment type (empty, wall, ore) of the tile at pos."""
        ...

    def get_tile_building_id(self, pos: Position) -> int | None:
        """Return the id of the building on the tile at pos, or None if there is none."""
        ...

    def get_tile_builder_bot_id(self, pos: Position) -> int | None:
        """Return the id of the builder bot on the tile at pos, or None if there is none."""
        ...

    def is_tile_empty(self, pos: Position) -> bool:
        """Return True if the tile has no building and is not a wall."""
        ...

    def is_tile_passable(self, pos: Position) -> bool:
        """Return True if a builder bot belonging to this team could stand on the tile
        (i.e. it contains a conveyor, road, or allied core, and no other builder bot)."""
        ...

    def is_in_vision(self, pos: Position) -> bool:
        """Return True if pos is within this unit's vision radius."""
        ...

    def get_nearby_tiles(self, dist_sq: int | None = None) -> list[Position]:
        """Return all in-bounds tile positions within dist_sq of this unit (defaults to vision radius).
        dist_sq must not exceed the vision radius."""
        ...

    def get_nearby_entities(self, dist_sq: int | None = None) -> list[int]:
        """Return ids of all entities on tiles within dist_sq (defaults to vision radius)."""
        ...

    def get_nearby_buildings(self, dist_sq: int | None = None) -> list[int]:
        """Return ids of all buildings within dist_sq (defaults to vision radius)."""
        ...

    def get_nearby_units(self, dist_sq: int | None = None) -> list[int]:
        """Return ids of all units within dist_sq (defaults to vision radius)."""
        ...

    def get_map_width(self) -> int:
        """Return the width of the map in tiles."""
        ...

    def get_map_height(self) -> int:
        """Return the height of the map in tiles."""
        ...

    def get_current_round(self) -> int:
        """Return the current round number (starts at 1)."""
        ...

    def get_global_resources(self) -> tuple[int, int]:
        """Return (titanium, axionite) in this team's global resource pool."""
        ...

    def get_scale_percent(self) -> float:
        """Return this team's current cost scale as a percentage (100.0 = base cost; used in the scaling formula)."""
        ...

    def get_cpu_time_elapsed(self) -> int:
        """Return the CPU time elapsed this turn in microseconds."""
        ...

    # --- Cost getters ---

    def get_conveyor_cost(self) -> tuple[int, int]:
        """Return the current scaled cost (Ti, Ax) to build a conveyor."""
        ...

    def get_splitter_cost(self) -> tuple[int, int]:
        """Return the current scaled cost (Ti, Ax) to build a splitter."""
        ...

    def get_bridge_cost(self) -> tuple[int, int]:
        """Return the current scaled cost (Ti, Ax) to build a bridge."""
        ...

    def get_armoured_conveyor_cost(self) -> tuple[int, int]:
        """Return the current scaled cost (Ti, Ax) to build an armoured conveyor."""
        ...

    def get_harvester_cost(self) -> tuple[int, int]:
        """Return the current scaled cost (Ti, Ax) to build a harvester."""
        ...

    def get_road_cost(self) -> tuple[int, int]:
        """Return the current scaled cost (Ti, Ax) to build a road."""
        ...

    def get_barrier_cost(self) -> tuple[int, int]:
        """Return the current scaled cost (Ti, Ax) to build a barrier."""
        ...

    def get_gunner_cost(self) -> tuple[int, int]:
        """Return the current scaled cost (Ti, Ax) to build a gunner."""
        ...

    def get_sentinel_cost(self) -> tuple[int, int]:
        """Return the current scaled cost (Ti, Ax) to build a sentinel."""
        ...

    def get_breach_cost(self) -> tuple[int, int]:
        """Return the current scaled cost (Ti, Ax) to build a breach."""
        ...

    def get_launcher_cost(self) -> tuple[int, int]:
        """Return the current scaled cost (Ti, Ax) to build a launcher."""
        ...

    def get_foundry_cost(self) -> tuple[int, int]:
        """Return the current scaled cost (Ti, Ax) to build an axionite foundry."""
        ...

    def get_builder_bot_cost(self) -> tuple[int, int]:
        """Return the current scaled cost (Ti, Ax) to spawn a builder bot."""
        ...

    # --- Movement ---

    def move(self, direction: Direction) -> None:
        """Move this builder bot one step in direction. Raises GameError if the move is not legal."""
        ...

    def can_move(self, direction: Direction) -> bool:
        """Return True if this builder bot can move in direction this turn."""
        ...

    # --- Building ---

    def can_build_conveyor(self, position: Position, direction: Direction) -> bool:
        """Return True if a conveyor facing direction can be built at position."""
        ...

    def can_build_splitter(self, position: Position, direction: Direction) -> bool:
        """Return True if a splitter facing direction can be built at position."""
        ...

    def can_build_bridge(self, position: Position, target: Position) -> bool:
        """Return True if a bridge outputting to target can be built at position.
        target must be within distance_squared BRIDGE_TARGET_RADIUS_SQ of position."""
        ...

    def can_build_armoured_conveyor(self, position: Position, direction: Direction) -> bool:
        """Return True if an armoured conveyor facing direction can be built at position."""
        ...

    def can_build_harvester(self, position: Position) -> bool:
        """Return True if a harvester can be built at position (must be an ore tile)."""
        ...

    def can_build_road(self, position: Position) -> bool:
        """Return True if a road can be built at position."""
        ...

    def can_build_barrier(self, position: Position) -> bool:
        """Return True if a barrier can be built at position."""
        ...

    def can_build_gunner(self, position: Position, direction: Direction) -> bool:
        """Return True if a gunner facing direction can be built at position."""
        ...

    def can_build_sentinel(self, position: Position, direction: Direction) -> bool:
        """Return True if a sentinel facing direction can be built at position."""
        ...

    def can_build_breach(self, position: Position, direction: Direction) -> bool:
        """Return True if a breach facing direction can be built at position."""
        ...

    def can_build_launcher(self, position: Position) -> bool:
        """Return True if a launcher can be built at position."""
        ...

    def can_build_foundry(self, position: Position) -> bool:
        """Return True if an axionite foundry can be built at position."""
        ...

    def build_conveyor(self, position: Position, direction: Direction) -> int:
        """Build a conveyor facing direction at position. Raises GameError if not legal."""
        ...

    def build_splitter(self, position: Position, direction: Direction) -> int:
        """Build a splitter facing direction at position. Raises GameError if not legal."""
        ...

    def build_bridge(self, position: Position, target: Position) -> int:
        """Build a bridge at position outputting to target. Raises GameError if not legal."""
        ...

    def build_armoured_conveyor(self, position: Position, direction: Direction) -> int:
        """Build an armoured conveyor facing direction at position. Raises GameError if not legal."""
        ...

    def build_harvester(self, position: Position) -> int:
        """Build a harvester at position (must be an ore tile). Raises GameError if not legal."""
        ...

    def build_road(self, position: Position) -> int:
        """Build a road at position. Raises GameError if not legal."""
        ...

    def build_barrier(self, position: Position) -> int:
        """Build a barrier at position. Raises GameError if not legal."""
        ...

    def build_gunner(self, position: Position, direction: Direction) -> int:
        """Build a gunner facing direction at position. Raises GameError if not legal."""
        ...

    def build_sentinel(self, position: Position, direction: Direction) -> int:
        """Build a sentinel facing direction at position. Raises GameError if not legal."""
        ...

    def build_breach(self, position: Position, direction: Direction) -> int:
        """Build a breach facing direction at position. Raises GameError if not legal."""
        ...

    def build_launcher(self, position: Position) -> int:
        """Build a launcher at position. Raises GameError if not legal."""
        ...

    def build_foundry(self, position: Position) -> int:
        """Build an axionite foundry at position. Raises GameError if not legal."""
        ...

    # --- Healing ---

    def heal(self, position: Position) -> None:
        """Heal all friendly entities on the tile at position by 10 HP. Costs one action cooldown.
        Raises GameError if not legal."""
        ...

    def can_heal(self, position: Position) -> bool:
        """Return True if this builder bot can heal the tile at position this turn.
        Requires action cooldown == 0 and at least one friendly entity on the tile."""
        ...

    # --- Destruction ---

    def can_destroy(self, building_pos: Position) -> bool:
        """Return True if this builder bot can destroy the allied building at building_pos."""
        ...

    def destroy(self, building_pos: Position) -> None:
        """Destroy the allied building at building_pos. Does not cost action cooldown.
        Raises GameError if not legal."""
        ...

    def self_destruct(self) -> None:
        """Destroy this unit. If it is a builder bot, deals 20 damage to the tile it stands on."""
        ...

    def resign(self) -> None:
        """Forfeit the game immediately. Destroys this team's core, ending the game as a loss."""
        ...

    # --- Markers ---

    def can_place_marker(self, position: Position) -> bool:
        """Return True if this unit can place a marker at position this turn.
        Each unit may place at most one marker per turn; cannot overwrite enemy markers."""
        ...

    def place_marker(self, position: Position, value: int) -> None:
        """Place a marker with the given u32 value at position. Does not cost action cooldown.
        Raises GameError if not legal."""
        ...

    def get_marker_value(self, id: int) -> int:
        """Return the u32 value stored in the friendly marker with the given id.
        Raises GameError if the entity is not a marker or belongs to the enemy."""
        ...

    # --- Turrets ---

    def can_fire(self, target: Position) -> bool:
        """Return True if this turret can fire at target this turn.
        Use can_launch() instead for launchers."""
        ...

    def fire(self, target: Position) -> None:
        """Fire this turret at target. Use launch() instead for launchers.
        Raises GameError if not legal."""
        ...

    def get_gunner_target(self) -> Position | None:
        """Return the position of the closest nonempty tile in the gunner's facing direction,
        or None if nothing is in range. Only valid on gunners."""
        ...

    def can_launch(self, bot_pos: Position, target: Position) -> bool:
        """Return True if this launcher can pick up the builder bot at bot_pos and throw it to target."""
        ...

    def launch(self, bot_pos: Position, target: Position) -> None:
        """Pick up the builder bot at bot_pos and throw it to target.
        Raises GameError if not legal."""
        ...

    # --- Core ---

    def spawn_builder(self, position: Position) -> int:
        """Spawn a builder bot on one of the 9 core tiles at position. Costs one action cooldown.
        Raises GameError if not legal."""
        ...

    def can_spawn(self, position: Position) -> bool:
        """Return True if the core can spawn a builder bot at position this turn."""
        ...

    # --- Indicators ---

    def draw_indicator_line(self, pos_a: Position, pos_b: Position, r: int, g: int, b: int) -> None:
        """Draw a debug line from pos_a to pos_b with RGB colour. Saved to the replay."""
        ...

    def draw_indicator_dot(self, pos: Position, r: int, g: int, b: int) -> None:
        """Draw a debug dot at pos with RGB colour. Saved to the replay."""
        ...
