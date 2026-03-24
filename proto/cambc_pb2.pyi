"""Type stubs for proto/cambc_pb2 (generated from cambc.proto)."""

from collections.abc import Sequence
from typing import Any

class Pos:
    x: int
    y: int

class CorePosition:
    id: int
    team: int
    position: Pos

class TileRow:
    tiles: Sequence[int]

class Map:
    width: int
    height: int
    rows: Sequence[TileRow]
    cores: Sequence[CorePosition]

class Player:
    titanium: int
    axionite: int
    resources_collected: int
    titanium_collected: int
    axionite_collected: int

class Players:
    a: Player
    b: Player

class Entity:
    id: int
    team: int
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
    def WhichOneof(self, oneof_name: str) -> str | None: ...
    def HasField(self, field_name: str) -> bool: ...

class BuilderBot:
    action_cooldown: int
    move_cooldown: int

class Conveyor:
    direction: int
    stored: int

class Splitter:
    direction: int
    stored: int

class ArmouredConveyor:
    direction: int
    stored: int

class Bridge:
    target: Pos
    stored: int

class Harvester:
    cooldown: int
    resource_type: int

class Foundry:
    stored: int

class Road: ...
class Barrier: ...

class Marker:
    value: int

class Core:
    action_cooldown: int

class Gunner:
    direction: int
    ammo_type: int
    ammo_amount: int

class Sentinel:
    direction: int
    ammo_type: int
    ammo_amount: int

class Breach:
    direction: int
    ammo_type: int
    ammo_amount: int

class Launcher:
    ammo_type: int
    ammo_amount: int

class PlaceEntity:
    entity: Entity

class MoveBuilderBot:
    id: int
    to: Pos

class RemoveEntity:
    id: int

class ResourceMove:
    to: Pos

class DistributeResources:
    moves: Sequence[ResourceMove]

class UpdateHp:
    id: int
    delta: int

class UpdatePlayers:
    players: Players

class BotOutput:
    id: int
    stdout: str
    output: str
    exec_time_us: int
    tled: bool

class FireTurret:
    to: Pos

class UpdateResources:
    team: int
    titanium: int

class Update:
    place_entity: PlaceEntity
    move_builder_bot: MoveBuilderBot
    remove_entity: RemoveEntity
    distribute_resources: DistributeResources
    update_hp: UpdateHp
    update_players: UpdatePlayers
    update_resources: UpdateResources
    bot_output: BotOutput
    fire_turret: FireTurret
    def WhichOneof(self, oneof_name: str) -> str | None: ...
    def HasField(self, field_name: str) -> bool: ...
    def ListFields(self) -> list[tuple[Any, Any]]: ...

class Turn:
    updates: Sequence[Update]

class Replay:
    map: Map
    turns: Sequence[Turn]
    winner: int
    def ParseFromString(self, data: bytes) -> int: ...
    def HasField(self, field_name: str) -> bool: ...
