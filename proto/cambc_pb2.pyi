from collections.abc import Iterable as _Iterable
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper

DESCRIPTOR: _descriptor.FileDescriptor

class Team(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TEAM_A: _ClassVar[Team]
    TEAM_B: _ClassVar[Team]

class Direction(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    DIR_CENTRE: _ClassVar[Direction]
    DIR_NORTH: _ClassVar[Direction]
    DIR_NORTHEAST: _ClassVar[Direction]
    DIR_EAST: _ClassVar[Direction]
    DIR_SOUTHEAST: _ClassVar[Direction]
    DIR_SOUTH: _ClassVar[Direction]
    DIR_SOUTHWEST: _ClassVar[Direction]
    DIR_WEST: _ClassVar[Direction]
    DIR_NORTHWEST: _ClassVar[Direction]

class ResourceType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    RESOURCE_NONE: _ClassVar[ResourceType]
    RESOURCE_TITANIUM: _ClassVar[ResourceType]
    RESOURCE_RAW_AXIONITE: _ClassVar[ResourceType]
    RESOURCE_REFINED_AXIONITE: _ClassVar[ResourceType]

class Environment(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ENV_EMPTY: _ClassVar[Environment]
    ENV_WALL: _ClassVar[Environment]
    ENV_ORE_TITANIUM: _ClassVar[Environment]
    ENV_ORE_AXIONITE: _ClassVar[Environment]
TEAM_A: Team
TEAM_B: Team
DIR_CENTRE: Direction
DIR_NORTH: Direction
DIR_NORTHEAST: Direction
DIR_EAST: Direction
DIR_SOUTHEAST: Direction
DIR_SOUTH: Direction
DIR_SOUTHWEST: Direction
DIR_WEST: Direction
DIR_NORTHWEST: Direction
RESOURCE_NONE: ResourceType
RESOURCE_TITANIUM: ResourceType
RESOURCE_RAW_AXIONITE: ResourceType
RESOURCE_REFINED_AXIONITE: ResourceType
ENV_EMPTY: Environment
ENV_WALL: Environment
ENV_ORE_TITANIUM: Environment
ENV_ORE_AXIONITE: Environment

class Replay(_message.Message):
    __slots__ = ("map", "turns", "winner")
    MAP_FIELD_NUMBER: _ClassVar[int]
    TURNS_FIELD_NUMBER: _ClassVar[int]
    WINNER_FIELD_NUMBER: _ClassVar[int]
    map: Map
    turns: _containers.RepeatedCompositeFieldContainer[Turn]
    winner: Team
    def __init__(self, map: Map | _Mapping | None = ..., turns: _Iterable[Turn | _Mapping] | None = ..., winner: Team | str | None = ...) -> None: ...

class Map(_message.Message):
    __slots__ = ("cores", "height", "rows", "width")
    WIDTH_FIELD_NUMBER: _ClassVar[int]
    HEIGHT_FIELD_NUMBER: _ClassVar[int]
    ROWS_FIELD_NUMBER: _ClassVar[int]
    CORES_FIELD_NUMBER: _ClassVar[int]
    width: int
    height: int
    rows: _containers.RepeatedCompositeFieldContainer[TileRow]
    cores: _containers.RepeatedCompositeFieldContainer[CorePosition]
    def __init__(self, width: int | None = ..., height: int | None = ..., rows: _Iterable[TileRow | _Mapping] | None = ..., cores: _Iterable[CorePosition | _Mapping] | None = ...) -> None: ...

class TileRow(_message.Message):
    __slots__ = ("tiles",)
    TILES_FIELD_NUMBER: _ClassVar[int]
    tiles: _containers.RepeatedScalarFieldContainer[Environment]
    def __init__(self, tiles: _Iterable[Environment | str] | None = ...) -> None: ...

class Players(_message.Message):
    __slots__ = ("a", "b")
    A_FIELD_NUMBER: _ClassVar[int]
    B_FIELD_NUMBER: _ClassVar[int]
    a: Player
    b: Player
    def __init__(self, a: Player | _Mapping | None = ..., b: Player | _Mapping | None = ...) -> None: ...

class Player(_message.Message):
    __slots__ = ("axionite", "axionite_collected", "resources_collected", "titanium", "titanium_collected")
    TITANIUM_FIELD_NUMBER: _ClassVar[int]
    AXIONITE_FIELD_NUMBER: _ClassVar[int]
    RESOURCES_COLLECTED_FIELD_NUMBER: _ClassVar[int]
    TITANIUM_COLLECTED_FIELD_NUMBER: _ClassVar[int]
    AXIONITE_COLLECTED_FIELD_NUMBER: _ClassVar[int]
    titanium: int
    axionite: int
    resources_collected: int
    titanium_collected: int
    axionite_collected: int
    def __init__(self, titanium: int | None = ..., axionite: int | None = ..., resources_collected: int | None = ..., titanium_collected: int | None = ..., axionite_collected: int | None = ...) -> None: ...

class Turn(_message.Message):
    __slots__ = ("updates",)
    UPDATES_FIELD_NUMBER: _ClassVar[int]
    updates: _containers.RepeatedCompositeFieldContainer[Update]
    def __init__(self, updates: _Iterable[Update | _Mapping] | None = ...) -> None: ...

class Update(_message.Message):
    __slots__ = ("bot_output", "distribute_resources", "fire_turret", "indicator_dot", "indicator_line", "move_builder_bot", "place_entity", "remove_entity", "set_action_cooldown", "set_move_cooldown", "update_hp", "update_players")
    PLACE_ENTITY_FIELD_NUMBER: _ClassVar[int]
    MOVE_BUILDER_BOT_FIELD_NUMBER: _ClassVar[int]
    REMOVE_ENTITY_FIELD_NUMBER: _ClassVar[int]
    DISTRIBUTE_RESOURCES_FIELD_NUMBER: _ClassVar[int]
    UPDATE_HP_FIELD_NUMBER: _ClassVar[int]
    UPDATE_PLAYERS_FIELD_NUMBER: _ClassVar[int]
    SET_ACTION_COOLDOWN_FIELD_NUMBER: _ClassVar[int]
    SET_MOVE_COOLDOWN_FIELD_NUMBER: _ClassVar[int]
    BOT_OUTPUT_FIELD_NUMBER: _ClassVar[int]
    INDICATOR_LINE_FIELD_NUMBER: _ClassVar[int]
    INDICATOR_DOT_FIELD_NUMBER: _ClassVar[int]
    FIRE_TURRET_FIELD_NUMBER: _ClassVar[int]
    place_entity: PlaceEntity
    move_builder_bot: MoveBuilderBot
    remove_entity: RemoveEntity
    distribute_resources: DistributeResources
    update_hp: UpdateHp
    update_players: UpdatePlayers
    set_action_cooldown: SetActionCooldown
    set_move_cooldown: SetMoveCooldown
    bot_output: BotOutput
    indicator_line: IndicatorLine
    indicator_dot: IndicatorDot
    fire_turret: FireTurret
    def __init__(self, place_entity: PlaceEntity | _Mapping | None = ..., move_builder_bot: MoveBuilderBot | _Mapping | None = ..., remove_entity: RemoveEntity | _Mapping | None = ..., distribute_resources: DistributeResources | _Mapping | None = ..., update_hp: UpdateHp | _Mapping | None = ..., update_players: UpdatePlayers | _Mapping | None = ..., set_action_cooldown: SetActionCooldown | _Mapping | None = ..., set_move_cooldown: SetMoveCooldown | _Mapping | None = ..., bot_output: BotOutput | _Mapping | None = ..., indicator_line: IndicatorLine | _Mapping | None = ..., indicator_dot: IndicatorDot | _Mapping | None = ..., fire_turret: FireTurret | _Mapping | None = ...) -> None: ...

class PlaceEntity(_message.Message):
    __slots__ = ("entity",)
    ENTITY_FIELD_NUMBER: _ClassVar[int]
    entity: Entity
    def __init__(self, entity: Entity | _Mapping | None = ...) -> None: ...

class MoveBuilderBot(_message.Message):
    __slots__ = ("id", "to")
    ID_FIELD_NUMBER: _ClassVar[int]
    TO_FIELD_NUMBER: _ClassVar[int]
    id: int
    to: Pos
    def __init__(self, id: int | None = ..., to: Pos | _Mapping | None = ...) -> None: ...

class RemoveEntity(_message.Message):
    __slots__ = ("id",)
    ID_FIELD_NUMBER: _ClassVar[int]
    id: int
    def __init__(self, id: int | None = ...) -> None: ...

class DistributeResources(_message.Message):
    __slots__ = ("moves",)
    MOVES_FIELD_NUMBER: _ClassVar[int]
    moves: _containers.RepeatedCompositeFieldContainer[ResourceMove]
    def __init__(self, moves: _Iterable[ResourceMove | _Mapping] | None = ...) -> None: ...

class ResourceMove(_message.Message):
    __slots__ = ("to",)
    FROM_FIELD_NUMBER: _ClassVar[int]
    TO_FIELD_NUMBER: _ClassVar[int]
    to: Pos
    def __init__(self, to: Pos | _Mapping | None = ..., **kwargs) -> None: ...

class UpdateHp(_message.Message):
    __slots__ = ("delta", "id")
    ID_FIELD_NUMBER: _ClassVar[int]
    DELTA_FIELD_NUMBER: _ClassVar[int]
    id: int
    delta: int
    def __init__(self, id: int | None = ..., delta: int | None = ...) -> None: ...

class UpdatePlayers(_message.Message):
    __slots__ = ("players",)
    PLAYERS_FIELD_NUMBER: _ClassVar[int]
    players: Players
    def __init__(self, players: Players | _Mapping | None = ...) -> None: ...

class SetActionCooldown(_message.Message):
    __slots__ = ("id", "value")
    ID_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    id: int
    value: int
    def __init__(self, id: int | None = ..., value: int | None = ...) -> None: ...

class SetMoveCooldown(_message.Message):
    __slots__ = ("id", "value")
    ID_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    id: int
    value: int
    def __init__(self, id: int | None = ..., value: int | None = ...) -> None: ...

class BotOutput(_message.Message):
    __slots__ = ("exec_time_us", "id", "stdout", "tled")
    ID_FIELD_NUMBER: _ClassVar[int]
    STDOUT_FIELD_NUMBER: _ClassVar[int]
    EXEC_TIME_US_FIELD_NUMBER: _ClassVar[int]
    TLED_FIELD_NUMBER: _ClassVar[int]
    id: int
    stdout: str
    exec_time_us: int
    tled: bool
    def __init__(self, id: int | None = ..., stdout: str | None = ..., exec_time_us: int | None = ..., tled: bool = ...) -> None: ...

class IndicatorLine(_message.Message):
    __slots__ = ("b", "g", "id", "pos_a", "pos_b", "r")
    ID_FIELD_NUMBER: _ClassVar[int]
    POS_A_FIELD_NUMBER: _ClassVar[int]
    POS_B_FIELD_NUMBER: _ClassVar[int]
    R_FIELD_NUMBER: _ClassVar[int]
    G_FIELD_NUMBER: _ClassVar[int]
    B_FIELD_NUMBER: _ClassVar[int]
    id: int
    pos_a: Pos
    pos_b: Pos
    r: int
    g: int
    b: int
    def __init__(self, id: int | None = ..., pos_a: Pos | _Mapping | None = ..., pos_b: Pos | _Mapping | None = ..., r: int | None = ..., g: int | None = ..., b: int | None = ...) -> None: ...

class IndicatorDot(_message.Message):
    __slots__ = ("b", "g", "id", "pos", "r")
    ID_FIELD_NUMBER: _ClassVar[int]
    POS_FIELD_NUMBER: _ClassVar[int]
    R_FIELD_NUMBER: _ClassVar[int]
    G_FIELD_NUMBER: _ClassVar[int]
    B_FIELD_NUMBER: _ClassVar[int]
    id: int
    pos: Pos
    r: int
    g: int
    b: int
    def __init__(self, id: int | None = ..., pos: Pos | _Mapping | None = ..., r: int | None = ..., g: int | None = ..., b: int | None = ...) -> None: ...

class FireTurret(_message.Message):
    __slots__ = ("to",)
    FROM_FIELD_NUMBER: _ClassVar[int]
    TO_FIELD_NUMBER: _ClassVar[int]
    to: Pos
    def __init__(self, to: Pos | _Mapping | None = ..., **kwargs) -> None: ...

class Pos(_message.Message):
    __slots__ = ("x", "y")
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    x: int
    y: int
    def __init__(self, x: int | None = ..., y: int | None = ...) -> None: ...

class CorePosition(_message.Message):
    __slots__ = ("id", "position", "team")
    ID_FIELD_NUMBER: _ClassVar[int]
    TEAM_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    id: int
    team: Team
    position: Pos
    def __init__(self, id: int | None = ..., team: Team | str | None = ..., position: Pos | _Mapping | None = ...) -> None: ...

class Entity(_message.Message):
    __slots__ = ("armoured_conveyor", "barrier", "breach", "bridge", "builder_bot", "conveyor", "core", "foundry", "gunner", "harvester", "hp", "id", "launcher", "marker", "max_hp", "position", "road", "sentinel", "splitter", "team")
    ID_FIELD_NUMBER: _ClassVar[int]
    TEAM_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    HP_FIELD_NUMBER: _ClassVar[int]
    MAX_HP_FIELD_NUMBER: _ClassVar[int]
    BUILDER_BOT_FIELD_NUMBER: _ClassVar[int]
    CONVEYOR_FIELD_NUMBER: _ClassVar[int]
    SPLITTER_FIELD_NUMBER: _ClassVar[int]
    ARMOURED_CONVEYOR_FIELD_NUMBER: _ClassVar[int]
    BRIDGE_FIELD_NUMBER: _ClassVar[int]
    HARVESTER_FIELD_NUMBER: _ClassVar[int]
    FOUNDRY_FIELD_NUMBER: _ClassVar[int]
    ROAD_FIELD_NUMBER: _ClassVar[int]
    BARRIER_FIELD_NUMBER: _ClassVar[int]
    MARKER_FIELD_NUMBER: _ClassVar[int]
    CORE_FIELD_NUMBER: _ClassVar[int]
    GUNNER_FIELD_NUMBER: _ClassVar[int]
    SENTINEL_FIELD_NUMBER: _ClassVar[int]
    BREACH_FIELD_NUMBER: _ClassVar[int]
    LAUNCHER_FIELD_NUMBER: _ClassVar[int]
    id: int
    team: Team
    position: Pos
    hp: int
    max_hp: int
    builder_bot: BuilderBot
    conveyor: Conveyor
    splitter: Splitter
    armoured_conveyor: ArmouredConveyor
    bridge: Bridge
    harvester: Harvester
    foundry: Foundry
    road: Road
    barrier: Barrier
    marker: Marker
    core: Core
    gunner: Gunner
    sentinel: Sentinel
    breach: Breach
    launcher: Launcher
    def __init__(self, id: int | None = ..., team: Team | str | None = ..., position: Pos | _Mapping | None = ..., hp: int | None = ..., max_hp: int | None = ..., builder_bot: BuilderBot | _Mapping | None = ..., conveyor: Conveyor | _Mapping | None = ..., splitter: Splitter | _Mapping | None = ..., armoured_conveyor: ArmouredConveyor | _Mapping | None = ..., bridge: Bridge | _Mapping | None = ..., harvester: Harvester | _Mapping | None = ..., foundry: Foundry | _Mapping | None = ..., road: Road | _Mapping | None = ..., barrier: Barrier | _Mapping | None = ..., marker: Marker | _Mapping | None = ..., core: Core | _Mapping | None = ..., gunner: Gunner | _Mapping | None = ..., sentinel: Sentinel | _Mapping | None = ..., breach: Breach | _Mapping | None = ..., launcher: Launcher | _Mapping | None = ...) -> None: ...

class BuilderBot(_message.Message):
    __slots__ = ("action_cooldown", "move_cooldown")
    ACTION_COOLDOWN_FIELD_NUMBER: _ClassVar[int]
    MOVE_COOLDOWN_FIELD_NUMBER: _ClassVar[int]
    action_cooldown: int
    move_cooldown: int
    def __init__(self, action_cooldown: int | None = ..., move_cooldown: int | None = ...) -> None: ...

class Conveyor(_message.Message):
    __slots__ = ("direction", "stored")
    DIRECTION_FIELD_NUMBER: _ClassVar[int]
    STORED_FIELD_NUMBER: _ClassVar[int]
    direction: Direction
    stored: ResourceType
    def __init__(self, direction: Direction | str | None = ..., stored: ResourceType | str | None = ...) -> None: ...

class Splitter(_message.Message):
    __slots__ = ("direction", "stored")
    DIRECTION_FIELD_NUMBER: _ClassVar[int]
    STORED_FIELD_NUMBER: _ClassVar[int]
    direction: Direction
    stored: ResourceType
    def __init__(self, direction: Direction | str | None = ..., stored: ResourceType | str | None = ...) -> None: ...

class ArmouredConveyor(_message.Message):
    __slots__ = ("direction", "stored")
    DIRECTION_FIELD_NUMBER: _ClassVar[int]
    STORED_FIELD_NUMBER: _ClassVar[int]
    direction: Direction
    stored: ResourceType
    def __init__(self, direction: Direction | str | None = ..., stored: ResourceType | str | None = ...) -> None: ...

class Bridge(_message.Message):
    __slots__ = ("stored", "target")
    TARGET_FIELD_NUMBER: _ClassVar[int]
    STORED_FIELD_NUMBER: _ClassVar[int]
    target: Pos
    stored: ResourceType
    def __init__(self, target: Pos | _Mapping | None = ..., stored: ResourceType | str | None = ...) -> None: ...

class Harvester(_message.Message):
    __slots__ = ("cooldown", "resource_type")
    COOLDOWN_FIELD_NUMBER: _ClassVar[int]
    RESOURCE_TYPE_FIELD_NUMBER: _ClassVar[int]
    cooldown: int
    resource_type: ResourceType
    def __init__(self, cooldown: int | None = ..., resource_type: ResourceType | str | None = ...) -> None: ...

class Foundry(_message.Message):
    __slots__ = ("stored",)
    STORED_FIELD_NUMBER: _ClassVar[int]
    stored: ResourceType
    def __init__(self, stored: ResourceType | str | None = ...) -> None: ...

class Road(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class Barrier(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class Marker(_message.Message):
    __slots__ = ("value",)
    VALUE_FIELD_NUMBER: _ClassVar[int]
    value: int
    def __init__(self, value: int | None = ...) -> None: ...

class Core(_message.Message):
    __slots__ = ("action_cooldown",)
    ACTION_COOLDOWN_FIELD_NUMBER: _ClassVar[int]
    action_cooldown: int
    def __init__(self, action_cooldown: int | None = ...) -> None: ...

class Gunner(_message.Message):
    __slots__ = ("ammo_amount", "ammo_type", "direction")
    DIRECTION_FIELD_NUMBER: _ClassVar[int]
    AMMO_TYPE_FIELD_NUMBER: _ClassVar[int]
    AMMO_AMOUNT_FIELD_NUMBER: _ClassVar[int]
    direction: Direction
    ammo_type: ResourceType
    ammo_amount: int
    def __init__(self, direction: Direction | str | None = ..., ammo_type: ResourceType | str | None = ..., ammo_amount: int | None = ...) -> None: ...

class Sentinel(_message.Message):
    __slots__ = ("ammo_amount", "ammo_type", "direction")
    DIRECTION_FIELD_NUMBER: _ClassVar[int]
    AMMO_TYPE_FIELD_NUMBER: _ClassVar[int]
    AMMO_AMOUNT_FIELD_NUMBER: _ClassVar[int]
    direction: Direction
    ammo_type: ResourceType
    ammo_amount: int
    def __init__(self, direction: Direction | str | None = ..., ammo_type: ResourceType | str | None = ..., ammo_amount: int | None = ...) -> None: ...

class Breach(_message.Message):
    __slots__ = ("ammo_amount", "ammo_type", "direction")
    DIRECTION_FIELD_NUMBER: _ClassVar[int]
    AMMO_TYPE_FIELD_NUMBER: _ClassVar[int]
    AMMO_AMOUNT_FIELD_NUMBER: _ClassVar[int]
    direction: Direction
    ammo_type: ResourceType
    ammo_amount: int
    def __init__(self, direction: Direction | str | None = ..., ammo_type: ResourceType | str | None = ..., ammo_amount: int | None = ...) -> None: ...

class Launcher(_message.Message):
    __slots__ = ("ammo_amount", "ammo_type")
    AMMO_TYPE_FIELD_NUMBER: _ClassVar[int]
    AMMO_AMOUNT_FIELD_NUMBER: _ClassVar[int]
    ammo_type: ResourceType
    ammo_amount: int
    def __init__(self, ammo_type: ResourceType | str | None = ..., ammo_amount: int | None = ...) -> None: ...
