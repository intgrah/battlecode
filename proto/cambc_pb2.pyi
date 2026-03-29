from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

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
    def __init__(self, map: _Optional[_Union[Map, _Mapping]] = ..., turns: _Optional[_Iterable[_Union[Turn, _Mapping]]] = ..., winner: _Optional[_Union[Team, str]] = ...) -> None: ...

class Map(_message.Message):
    __slots__ = ("width", "height", "rows", "cores")
    WIDTH_FIELD_NUMBER: _ClassVar[int]
    HEIGHT_FIELD_NUMBER: _ClassVar[int]
    ROWS_FIELD_NUMBER: _ClassVar[int]
    CORES_FIELD_NUMBER: _ClassVar[int]
    width: int
    height: int
    rows: _containers.RepeatedCompositeFieldContainer[TileRow]
    cores: _containers.RepeatedCompositeFieldContainer[CorePosition]
    def __init__(self, width: _Optional[int] = ..., height: _Optional[int] = ..., rows: _Optional[_Iterable[_Union[TileRow, _Mapping]]] = ..., cores: _Optional[_Iterable[_Union[CorePosition, _Mapping]]] = ...) -> None: ...

class TileRow(_message.Message):
    __slots__ = ("tiles",)
    TILES_FIELD_NUMBER: _ClassVar[int]
    tiles: _containers.RepeatedScalarFieldContainer[Environment]
    def __init__(self, tiles: _Optional[_Iterable[_Union[Environment, str]]] = ...) -> None: ...

class Players(_message.Message):
    __slots__ = ("a", "b")
    A_FIELD_NUMBER: _ClassVar[int]
    B_FIELD_NUMBER: _ClassVar[int]
    a: Player
    b: Player
    def __init__(self, a: _Optional[_Union[Player, _Mapping]] = ..., b: _Optional[_Union[Player, _Mapping]] = ...) -> None: ...

class Player(_message.Message):
    __slots__ = ("titanium", "axionite", "resources_collected", "titanium_collected", "axionite_collected")
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
    def __init__(self, titanium: _Optional[int] = ..., axionite: _Optional[int] = ..., resources_collected: _Optional[int] = ..., titanium_collected: _Optional[int] = ..., axionite_collected: _Optional[int] = ...) -> None: ...

class Turn(_message.Message):
    __slots__ = ("updates",)
    UPDATES_FIELD_NUMBER: _ClassVar[int]
    updates: _containers.RepeatedCompositeFieldContainer[Update]
    def __init__(self, updates: _Optional[_Iterable[_Union[Update, _Mapping]]] = ...) -> None: ...

class Update(_message.Message):
    __slots__ = ("place_entity", "move_builder_bot", "remove_entity", "distribute_resources", "update_hp", "update_players", "set_action_cooldown", "set_move_cooldown", "bot_output", "indicator_line", "indicator_dot", "fire_turret")
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
    def __init__(self, place_entity: _Optional[_Union[PlaceEntity, _Mapping]] = ..., move_builder_bot: _Optional[_Union[MoveBuilderBot, _Mapping]] = ..., remove_entity: _Optional[_Union[RemoveEntity, _Mapping]] = ..., distribute_resources: _Optional[_Union[DistributeResources, _Mapping]] = ..., update_hp: _Optional[_Union[UpdateHp, _Mapping]] = ..., update_players: _Optional[_Union[UpdatePlayers, _Mapping]] = ..., set_action_cooldown: _Optional[_Union[SetActionCooldown, _Mapping]] = ..., set_move_cooldown: _Optional[_Union[SetMoveCooldown, _Mapping]] = ..., bot_output: _Optional[_Union[BotOutput, _Mapping]] = ..., indicator_line: _Optional[_Union[IndicatorLine, _Mapping]] = ..., indicator_dot: _Optional[_Union[IndicatorDot, _Mapping]] = ..., fire_turret: _Optional[_Union[FireTurret, _Mapping]] = ...) -> None: ...

class PlaceEntity(_message.Message):
    __slots__ = ("entity",)
    ENTITY_FIELD_NUMBER: _ClassVar[int]
    entity: Entity
    def __init__(self, entity: _Optional[_Union[Entity, _Mapping]] = ...) -> None: ...

class MoveBuilderBot(_message.Message):
    __slots__ = ("id", "to")
    ID_FIELD_NUMBER: _ClassVar[int]
    TO_FIELD_NUMBER: _ClassVar[int]
    id: int
    to: Pos
    def __init__(self, id: _Optional[int] = ..., to: _Optional[_Union[Pos, _Mapping]] = ...) -> None: ...

class RemoveEntity(_message.Message):
    __slots__ = ("id",)
    ID_FIELD_NUMBER: _ClassVar[int]
    id: int
    def __init__(self, id: _Optional[int] = ...) -> None: ...

class DistributeResources(_message.Message):
    __slots__ = ("moves",)
    MOVES_FIELD_NUMBER: _ClassVar[int]
    moves: _containers.RepeatedCompositeFieldContainer[ResourceMove]
    def __init__(self, moves: _Optional[_Iterable[_Union[ResourceMove, _Mapping]]] = ...) -> None: ...

class ResourceMove(_message.Message):
    __slots__ = ("to",)
    FROM_FIELD_NUMBER: _ClassVar[int]
    TO_FIELD_NUMBER: _ClassVar[int]
    to: Pos
    def __init__(self, to: _Optional[_Union[Pos, _Mapping]] = ..., **kwargs) -> None: ...

class UpdateHp(_message.Message):
    __slots__ = ("id", "delta")
    ID_FIELD_NUMBER: _ClassVar[int]
    DELTA_FIELD_NUMBER: _ClassVar[int]
    id: int
    delta: int
    def __init__(self, id: _Optional[int] = ..., delta: _Optional[int] = ...) -> None: ...

class UpdatePlayers(_message.Message):
    __slots__ = ("players",)
    PLAYERS_FIELD_NUMBER: _ClassVar[int]
    players: Players
    def __init__(self, players: _Optional[_Union[Players, _Mapping]] = ...) -> None: ...

class SetActionCooldown(_message.Message):
    __slots__ = ("id", "value")
    ID_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    id: int
    value: int
    def __init__(self, id: _Optional[int] = ..., value: _Optional[int] = ...) -> None: ...

class SetMoveCooldown(_message.Message):
    __slots__ = ("id", "value")
    ID_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    id: int
    value: int
    def __init__(self, id: _Optional[int] = ..., value: _Optional[int] = ...) -> None: ...

class BotOutput(_message.Message):
    __slots__ = ("id", "stdout", "exec_time_us", "tled")
    ID_FIELD_NUMBER: _ClassVar[int]
    STDOUT_FIELD_NUMBER: _ClassVar[int]
    EXEC_TIME_US_FIELD_NUMBER: _ClassVar[int]
    TLED_FIELD_NUMBER: _ClassVar[int]
    id: int
    stdout: str
    exec_time_us: int
    tled: bool
    def __init__(self, id: _Optional[int] = ..., stdout: _Optional[str] = ..., exec_time_us: _Optional[int] = ..., tled: bool = ...) -> None: ...

class IndicatorLine(_message.Message):
    __slots__ = ("id", "pos_a", "pos_b", "r", "g", "b")
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
    def __init__(self, id: _Optional[int] = ..., pos_a: _Optional[_Union[Pos, _Mapping]] = ..., pos_b: _Optional[_Union[Pos, _Mapping]] = ..., r: _Optional[int] = ..., g: _Optional[int] = ..., b: _Optional[int] = ...) -> None: ...

class IndicatorDot(_message.Message):
    __slots__ = ("id", "pos", "r", "g", "b")
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
    def __init__(self, id: _Optional[int] = ..., pos: _Optional[_Union[Pos, _Mapping]] = ..., r: _Optional[int] = ..., g: _Optional[int] = ..., b: _Optional[int] = ...) -> None: ...

class FireTurret(_message.Message):
    __slots__ = ("to",)
    FROM_FIELD_NUMBER: _ClassVar[int]
    TO_FIELD_NUMBER: _ClassVar[int]
    to: Pos
    def __init__(self, to: _Optional[_Union[Pos, _Mapping]] = ..., **kwargs) -> None: ...

class Pos(_message.Message):
    __slots__ = ("x", "y")
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    x: int
    y: int
    def __init__(self, x: _Optional[int] = ..., y: _Optional[int] = ...) -> None: ...

class CorePosition(_message.Message):
    __slots__ = ("id", "team", "position")
    ID_FIELD_NUMBER: _ClassVar[int]
    TEAM_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    id: int
    team: Team
    position: Pos
    def __init__(self, id: _Optional[int] = ..., team: _Optional[_Union[Team, str]] = ..., position: _Optional[_Union[Pos, _Mapping]] = ...) -> None: ...

class Entity(_message.Message):
    __slots__ = ("id", "team", "position", "hp", "max_hp", "builder_bot", "conveyor", "splitter", "armoured_conveyor", "bridge", "harvester", "foundry", "road", "barrier", "marker", "core", "gunner", "sentinel", "breach", "launcher")
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
    def __init__(self, id: _Optional[int] = ..., team: _Optional[_Union[Team, str]] = ..., position: _Optional[_Union[Pos, _Mapping]] = ..., hp: _Optional[int] = ..., max_hp: _Optional[int] = ..., builder_bot: _Optional[_Union[BuilderBot, _Mapping]] = ..., conveyor: _Optional[_Union[Conveyor, _Mapping]] = ..., splitter: _Optional[_Union[Splitter, _Mapping]] = ..., armoured_conveyor: _Optional[_Union[ArmouredConveyor, _Mapping]] = ..., bridge: _Optional[_Union[Bridge, _Mapping]] = ..., harvester: _Optional[_Union[Harvester, _Mapping]] = ..., foundry: _Optional[_Union[Foundry, _Mapping]] = ..., road: _Optional[_Union[Road, _Mapping]] = ..., barrier: _Optional[_Union[Barrier, _Mapping]] = ..., marker: _Optional[_Union[Marker, _Mapping]] = ..., core: _Optional[_Union[Core, _Mapping]] = ..., gunner: _Optional[_Union[Gunner, _Mapping]] = ..., sentinel: _Optional[_Union[Sentinel, _Mapping]] = ..., breach: _Optional[_Union[Breach, _Mapping]] = ..., launcher: _Optional[_Union[Launcher, _Mapping]] = ...) -> None: ...

class BuilderBot(_message.Message):
    __slots__ = ("action_cooldown", "move_cooldown")
    ACTION_COOLDOWN_FIELD_NUMBER: _ClassVar[int]
    MOVE_COOLDOWN_FIELD_NUMBER: _ClassVar[int]
    action_cooldown: int
    move_cooldown: int
    def __init__(self, action_cooldown: _Optional[int] = ..., move_cooldown: _Optional[int] = ...) -> None: ...

class Conveyor(_message.Message):
    __slots__ = ("direction", "stored")
    DIRECTION_FIELD_NUMBER: _ClassVar[int]
    STORED_FIELD_NUMBER: _ClassVar[int]
    direction: Direction
    stored: ResourceType
    def __init__(self, direction: _Optional[_Union[Direction, str]] = ..., stored: _Optional[_Union[ResourceType, str]] = ...) -> None: ...

class Splitter(_message.Message):
    __slots__ = ("direction", "stored")
    DIRECTION_FIELD_NUMBER: _ClassVar[int]
    STORED_FIELD_NUMBER: _ClassVar[int]
    direction: Direction
    stored: ResourceType
    def __init__(self, direction: _Optional[_Union[Direction, str]] = ..., stored: _Optional[_Union[ResourceType, str]] = ...) -> None: ...

class ArmouredConveyor(_message.Message):
    __slots__ = ("direction", "stored")
    DIRECTION_FIELD_NUMBER: _ClassVar[int]
    STORED_FIELD_NUMBER: _ClassVar[int]
    direction: Direction
    stored: ResourceType
    def __init__(self, direction: _Optional[_Union[Direction, str]] = ..., stored: _Optional[_Union[ResourceType, str]] = ...) -> None: ...

class Bridge(_message.Message):
    __slots__ = ("target", "stored")
    TARGET_FIELD_NUMBER: _ClassVar[int]
    STORED_FIELD_NUMBER: _ClassVar[int]
    target: Pos
    stored: ResourceType
    def __init__(self, target: _Optional[_Union[Pos, _Mapping]] = ..., stored: _Optional[_Union[ResourceType, str]] = ...) -> None: ...

class Harvester(_message.Message):
    __slots__ = ("cooldown", "resource_type")
    COOLDOWN_FIELD_NUMBER: _ClassVar[int]
    RESOURCE_TYPE_FIELD_NUMBER: _ClassVar[int]
    cooldown: int
    resource_type: ResourceType
    def __init__(self, cooldown: _Optional[int] = ..., resource_type: _Optional[_Union[ResourceType, str]] = ...) -> None: ...

class Foundry(_message.Message):
    __slots__ = ("stored",)
    STORED_FIELD_NUMBER: _ClassVar[int]
    stored: ResourceType
    def __init__(self, stored: _Optional[_Union[ResourceType, str]] = ...) -> None: ...

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
    def __init__(self, value: _Optional[int] = ...) -> None: ...

class Core(_message.Message):
    __slots__ = ("action_cooldown",)
    ACTION_COOLDOWN_FIELD_NUMBER: _ClassVar[int]
    action_cooldown: int
    def __init__(self, action_cooldown: _Optional[int] = ...) -> None: ...

class Gunner(_message.Message):
    __slots__ = ("direction", "ammo_type", "ammo_amount")
    DIRECTION_FIELD_NUMBER: _ClassVar[int]
    AMMO_TYPE_FIELD_NUMBER: _ClassVar[int]
    AMMO_AMOUNT_FIELD_NUMBER: _ClassVar[int]
    direction: Direction
    ammo_type: ResourceType
    ammo_amount: int
    def __init__(self, direction: _Optional[_Union[Direction, str]] = ..., ammo_type: _Optional[_Union[ResourceType, str]] = ..., ammo_amount: _Optional[int] = ...) -> None: ...

class Sentinel(_message.Message):
    __slots__ = ("direction", "ammo_type", "ammo_amount")
    DIRECTION_FIELD_NUMBER: _ClassVar[int]
    AMMO_TYPE_FIELD_NUMBER: _ClassVar[int]
    AMMO_AMOUNT_FIELD_NUMBER: _ClassVar[int]
    direction: Direction
    ammo_type: ResourceType
    ammo_amount: int
    def __init__(self, direction: _Optional[_Union[Direction, str]] = ..., ammo_type: _Optional[_Union[ResourceType, str]] = ..., ammo_amount: _Optional[int] = ...) -> None: ...

class Breach(_message.Message):
    __slots__ = ("direction", "ammo_type", "ammo_amount")
    DIRECTION_FIELD_NUMBER: _ClassVar[int]
    AMMO_TYPE_FIELD_NUMBER: _ClassVar[int]
    AMMO_AMOUNT_FIELD_NUMBER: _ClassVar[int]
    direction: Direction
    ammo_type: ResourceType
    ammo_amount: int
    def __init__(self, direction: _Optional[_Union[Direction, str]] = ..., ammo_type: _Optional[_Union[ResourceType, str]] = ..., ammo_amount: _Optional[int] = ...) -> None: ...

class Launcher(_message.Message):
    __slots__ = ("ammo_type", "ammo_amount")
    AMMO_TYPE_FIELD_NUMBER: _ClassVar[int]
    AMMO_AMOUNT_FIELD_NUMBER: _ClassVar[int]
    ammo_type: ResourceType
    ammo_amount: int
    def __init__(self, ammo_type: _Optional[_Union[ResourceType, str]] = ..., ammo_amount: _Optional[int] = ...) -> None: ...
