# ruff: noqa: A002

from __future__ import annotations

import copy
import gc
import heapq
import importlib.util
import math
import random
import re
import sys
import time
import traceback
import typing
from dataclasses import dataclass, field
from enum import Enum
from importlib.abc import Loader
from io import StringIO
from pathlib import Path
from typing import Final, NamedTuple, Protocol, cast

from proto import cambc_pb2 as pb

if typing.TYPE_CHECKING:
    import types
    from collections.abc import Sequence
    from importlib.machinery import ModuleSpec


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
    STARTING_TITANIUM = 500
    STARTING_AXIONITE = 0
    MAX_TEAM_UNITS = 50
    PASSIVE_TITANIUM_AMOUNT = 10
    PASSIVE_TITANIUM_INTERVAL = 4
    AXIONITE_CONVERSION_TITANIUM_RATE = 4

    ACTION_RADIUS_SQ = 2
    CORE_SPAWNING_RADIUS_SQ = 2
    CORE_ACTION_RADIUS_SQ = 8

    BRIDGE_TARGET_RADIUS_SQ = 9

    CORE_VISION_RADIUS_SQ = 36
    BUILDER_BOT_VISION_RADIUS_SQ = 20
    GUNNER_VISION_RADIUS_SQ = 13
    SENTINEL_VISION_RADIUS_SQ = 32
    BREACH_VISION_RADIUS_SQ = 2
    LAUNCHER_VISION_RADIUS_SQ = 26

    CONVEYOR_BASE_COST = (3, 0)
    SPLITTER_BASE_COST = (6, 0)
    BRIDGE_BASE_COST = (20, 0)
    ARMOURED_CONVEYOR_BASE_COST = (5, 5)
    HARVESTER_BASE_COST = (20, 0)
    ROAD_BASE_COST = (1, 0)
    BARRIER_BASE_COST = (3, 0)
    GUNNER_BASE_COST = (10, 0)
    SENTINEL_BASE_COST = (30, 0)
    BREACH_BASE_COST = (15, 10)
    LAUNCHER_BASE_COST = (20, 0)
    FOUNDRY_BASE_COST = (40, 0)
    BUILDER_BOT_BASE_COST = (30, 0)
    GUNNER_ROTATE_COST = (10, 0)
    GUNNER_ROTATE_COOLDOWN = 1

    CONVEYOR_MAX_HP = 20
    SPLITTER_MAX_HP = 20
    BRIDGE_MAX_HP = 20
    ARMOURED_CONVEYOR_MAX_HP = 50
    HARVESTER_MAX_HP = 30
    ROAD_MAX_HP = 4
    BARRIER_MAX_HP = 30
    FOUNDRY_MAX_HP = 50
    MARKER_MAX_HP = 1

    BUILDER_BOT_MAX_HP = 40
    CORE_MAX_HP = 500
    GUNNER_MAX_HP = 40
    SENTINEL_MAX_HP = 30
    BREACH_MAX_HP = 60
    LAUNCHER_MAX_HP = 30

    BUILDER_BOT_SELF_DESTRUCT_DAMAGE = 0
    BUILDER_BOT_ATTACK_DAMAGE = 2
    BUILDER_BOT_ATTACK_COST = (2, 0)
    BUILDER_BOT_HEAL_COST = (1, 0)
    HEAL_AMOUNT = 4

    GUNNER_DAMAGE = 10
    GUNNER_AXIONITE_DAMAGE = 25
    GUNNER_FIRE_COOLDOWN = 1
    GUNNER_AMMO_COST = 2

    SENTINEL_DAMAGE = 18
    SENTINEL_FIRE_COOLDOWN = 3
    SENTINEL_AMMO_COST = 10
    SENTINEL_STUN_DURATION = 5

    BREACH_DAMAGE = 40
    BREACH_SPLASH_DAMAGE = 20
    BREACH_FIRE_COOLDOWN = 1
    BREACH_AMMO_COST = 5
    BREACH_ATTACK_RADIUS_SQ = 24

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


_TEAM_IDX: dict[Team, int] = {Team.A: 0, Team.B: 1}
_IDX_TEAM: dict[int, Team] = {0: Team.A, 1: Team.B}

CARDINAL_DIRS: list[Direction] = [
    Direction.NORTH,
    Direction.EAST,
    Direction.SOUTH,
    Direction.WEST,
]

ALL_DIRS: list[Direction] = [
    Direction.NORTH,
    Direction.NORTHEAST,
    Direction.EAST,
    Direction.SOUTHEAST,
    Direction.SOUTH,
    Direction.SOUTHWEST,
    Direction.WEST,
    Direction.NORTHWEST,
]

ALL_DIRS_AND_CENTRE: list[Direction] = [*ALL_DIRS, Direction.CENTRE]

_ENV_INT: dict[int, Environment] = {
    0: Environment.EMPTY,
    1: Environment.WALL,
    2: Environment.ORE_TITANIUM,
    3: Environment.ORE_AXIONITE,
}


def _pos_add(x: int, y: int, direction: Direction) -> tuple[int, int]:
    dx, dy = direction.delta()
    return (x + dx, y + dy)


def _distance_squared(x1: int, y1: int, x2: int, y2: int) -> int:
    dx = x1 - x2
    dy = y1 - y2
    return dx * dx + dy * dy


@dataclass(slots=True)
class Tile:
    env: Environment
    building: int | None = None
    bot: int | None = None


@dataclass(slots=True)
class PlayerState:
    titanium: int = GameConstants.STARTING_TITANIUM
    axionite: int = GameConstants.STARTING_AXIONITE
    resources_collected: int = 0
    titanium_collected: int = 0
    axionite_collected: int = 0
    scale_milli: int = 1000


@dataclass(slots=True)
class EntityBase:
    id: int
    team: Team
    x: int
    y: int
    hp: int
    max_hp: int


@dataclass(slots=True)
class BuilderBot(EntityBase):
    action_cooldown: int = 0
    move_cooldown: int = 0


@dataclass(slots=True)
class Core(EntityBase):
    action_cooldown: int = 0
    move_cooldown: int = 0
    received: list[ResourceType] = field(default_factory=list)


@dataclass(slots=True)
class Conveyor(EntityBase):
    direction: Direction = Direction.NORTH
    stored: ResourceType | None = None
    stored_id: int | None = None


@dataclass(slots=True)
class Splitter(EntityBase):
    direction: Direction = Direction.NORTH
    stored: ResourceType | None = None
    stored_id: int | None = None


@dataclass(slots=True)
class ArmouredConveyor(EntityBase):
    direction: Direction = Direction.NORTH
    stored: ResourceType | None = None
    stored_id: int | None = None


@dataclass(slots=True)
class Bridge(EntityBase):
    target_x: int = 0
    target_y: int = 0
    stored: ResourceType | None = None
    stored_id: int | None = None


@dataclass(slots=True)
class Harvester(EntityBase):
    resource_type: ResourceType = ResourceType.TITANIUM
    cooldown: int = 0


@dataclass(slots=True)
class Foundry(EntityBase):
    stored: ResourceType | None = None
    stored_id: int | None = None


@dataclass(slots=True)
class Road(EntityBase):
    pass


@dataclass(slots=True)
class Barrier(EntityBase):
    pass


@dataclass(slots=True)
class Marker(EntityBase):
    value: int = 0


@dataclass(slots=True)
class Gunner(EntityBase):
    action_cooldown: int = 0
    move_cooldown: int = 0
    direction: Direction = Direction.NORTH
    ammo_type: ResourceType | None = None
    ammo_amount: int = 0


@dataclass(slots=True)
class Sentinel(EntityBase):
    action_cooldown: int = 0
    move_cooldown: int = 0
    direction: Direction = Direction.NORTH
    ammo_type: ResourceType | None = None
    ammo_amount: int = 0


@dataclass(slots=True)
class Breach(EntityBase):
    action_cooldown: int = 0
    move_cooldown: int = 0
    direction: Direction = Direction.NORTH
    ammo_type: ResourceType | None = None
    ammo_amount: int = 0


@dataclass(slots=True)
class Launcher(EntityBase):
    action_cooldown: int = 0
    move_cooldown: int = 0
    ammo_type: ResourceType | None = None
    ammo_amount: int = 0


Entity = (
    BuilderBot
    | Core
    | Conveyor
    | Splitter
    | ArmouredConveyor
    | Bridge
    | Harvester
    | Foundry
    | Road
    | Barrier
    | Marker
    | Gunner
    | Sentinel
    | Breach
    | Launcher
)
Unit = BuilderBot | Core | Gunner | Sentinel | Breach | Launcher
Turret = Gunner | Sentinel | Breach


@dataclass(slots=True)
class DiffPlaceEntity:
    entity: Entity


@dataclass(slots=True)
class DiffMove:
    id: int
    to_x: int
    to_y: int


@dataclass(slots=True)
class DiffRemove:
    id: int


@dataclass(slots=True)
class DiffDistribute:
    moves: list[tuple[int, int, int, int, int]]


@dataclass(slots=True)
class DiffUpdateHp:
    id: int
    delta: int


@dataclass(slots=True)
class DiffUpdatePlayers:
    players: list[PlayerState]


@dataclass(slots=True)
class DiffSetActionCooldown:
    id: int
    value: int


@dataclass(slots=True)
class DiffSetMoveCooldown:
    id: int
    value: int


@dataclass(slots=True)
class DiffBotOutput:
    id: int
    stdout: str
    exec_time_us: int
    tled: bool


@dataclass(slots=True)
class DiffIndicatorLine:
    x1: int
    y1: int
    x2: int
    y2: int
    r: int
    g: int
    b: int


@dataclass(slots=True)
class DiffIndicatorDot:
    x: int
    y: int
    r: int
    g: int
    b: int


@dataclass(slots=True)
class DiffFireTurret:
    from_x: int
    from_y: int
    to_x: int
    to_y: int


@dataclass(slots=True)
class DiffBuilderBotAttack:
    id: int


Diff = (
    DiffPlaceEntity
    | DiffMove
    | DiffRemove
    | DiffDistribute
    | DiffUpdateHp
    | DiffUpdatePlayers
    | DiffSetActionCooldown
    | DiffSetMoveCooldown
    | DiffBotOutput
    | DiffIndicatorLine
    | DiffIndicatorDot
    | DiffFireTurret
    | DiffBuilderBotAttack
)


def _is_unit(entity: Entity) -> bool:
    return isinstance(entity, (BuilderBot, Core, Gunner, Sentinel, Breach, Launcher))


def _is_passable_building(entity: Entity) -> bool:
    return isinstance(entity, (Conveyor, Splitter, ArmouredConveyor, Bridge, Road))


def scale_contribution(entity: Entity) -> int:
    match entity:
        case Conveyor() | Splitter() | ArmouredConveyor():
            return 10
        case Bridge():
            return 100
        case Road():
            return 5
        case Barrier():
            return 10
        case Harvester():
            return 50
        case Gunner() | Breach() | Launcher():
            return 100
        case Sentinel():
            return 200
        case Foundry():
            return 500
        case BuilderBot():
            return 200
        case Core() | Marker():
            return 0


def vision_radius_sq(entity: Entity) -> int:
    match entity:
        case BuilderBot():
            return GameConstants.BUILDER_BOT_VISION_RADIUS_SQ
        case Core():
            return GameConstants.CORE_VISION_RADIUS_SQ
        case Gunner():
            return GameConstants.GUNNER_VISION_RADIUS_SQ
        case Sentinel():
            return GameConstants.SENTINEL_VISION_RADIUS_SQ
        case Breach():
            return GameConstants.BREACH_VISION_RADIUS_SQ
        case Launcher():
            return GameConstants.LAUNCHER_VISION_RADIUS_SQ
        case _:
            return 0


def action_radius_sq(entity: Entity) -> int:
    match entity:
        case Core():
            return GameConstants.CORE_ACTION_RADIUS_SQ
        case Launcher():
            return GameConstants.ACTION_RADIUS_SQ
        case BuilderBot() | Gunner() | Sentinel() | Breach():
            return GameConstants.ACTION_RADIUS_SQ
        case _:
            return 0


class Game:
    def __init__(
        self,
        environment: list[list[int]],
        cores: list[tuple[int, int, int]],
        seed: int,
        *,
        suppress_indicators: bool = False,
    ) -> None:
        self.height: int = len(environment)
        self.width: int = len(environment[0]) if self.height > 0 else 0
        self.tiles: list[list[Tile]] = [
            [Tile(env=_ENV_INT[environment[y][x]]) for x in range(self.width)]
            for y in range(self.height)
        ]
        self.entities: dict[int, Entity] = {}
        self.players: list[PlayerState] = [PlayerState(), PlayerState()]
        self.unit_order: list[int] = []
        self.harvesters: list[int] = []
        self.turn: int = 0
        self.next_id: int = 2
        self.rng: Final[random.Random] = random.Random(seed)
        self.edge_last_used: dict[tuple[int, int, int, int], int] = {}
        self.suppress_indicators: Final[bool] = suppress_indicators
        self._environment: list[list[int]] = environment
        self._cores_init: list[tuple[int, int, int]] = cores
        self.replay_diffs: list[list[Diff]] = []
        self._current_diffs: list[Diff] = []
        self.resign_message: str | None = None

        for idx, (cx, cy, team_idx) in enumerate(cores):
            eid = idx + 1
            team = _IDX_TEAM[team_idx]
            core = Core(
                id=eid,
                team=team,
                x=cx,
                y=cy,
                hp=GameConstants.CORE_MAX_HP,
                max_hp=GameConstants.CORE_MAX_HP,
            )
            self.entities[eid] = core
            self.unit_order.append(eid)
            for d in ALL_DIRS_AND_CENTRE:
                px, py_ = _pos_add(cx, cy, d)
                assert self.in_bounds(px, py_)
                self.tiles[py_][px].building = eid

    def new_id(self) -> int:
        self.next_id += 1
        return self.next_id

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def tile(self, x: int, y: int) -> Tile:
        return self.tiles[y][x]

    def team_idx(self, team: Team) -> int:
        return _TEAM_IDX[team]

    def spend(self, team: Team, cost: tuple[int, int]) -> None:
        ti = _TEAM_IDX[team]
        self.players[ti].titanium -= cost[0]
        self.players[ti].axionite -= cost[1]

    def scaled_cost(self, team: Team, base: tuple[int, int]) -> tuple[int, int]:
        sm = self.players[_TEAM_IDX[team]].scale_milli
        return (base[0] * sm // 1000, base[1] * sm // 1000)

    def can_afford(self, team: Team, cost: tuple[int, int]) -> bool:
        ti = _TEAM_IDX[team]
        return (
            self.players[ti].titanium >= cost[0]
            and self.players[ti].axionite >= cost[1]
        )

    def is_tile_bot_passable(self, x: int, y: int, team: Team) -> bool:
        if not self.in_bounds(x, y):
            return False
        t = self.tiles[y][x]
        if t.bot is not None:
            return False
        bid = t.building
        if bid is None:
            return False
        entity = self.entities.get(bid)
        if entity is None:
            return False
        if _is_passable_building(entity):
            return True
        return isinstance(entity, Core) and entity.team is team

    def is_tile_empty(self, x: int, y: int) -> bool:
        t = self.tiles[y][x]
        return t.building is None and t.env is not Environment.WALL

    def unit_count(self, team: Team) -> int:
        count = 0
        for uid in self.unit_order:
            e = self.entities.get(uid)
            if e is not None and e.team is team:
                count += 1
        return count

    def has_core(self, team: Team) -> bool:
        for e in self.entities.values():
            if isinstance(e, Core) and e.team is team:
                return True
        return False

    def winner_team(self) -> tuple[Team | None, str]:
        alive: list[Team] = [t for t in Team if self.has_core(t)]
        if len(alive) == 1:
            return alive[0], "core_destroyed"
        if self.turn >= GameConstants.MAX_TURNS or len(alive) == 0:
            a = self.players[0]
            b = self.players[1]
            if a.axionite_collected != b.axionite_collected:
                w = Team.A if a.axionite_collected > b.axionite_collected else Team.B
                return w, "axionite_collected"
            if a.titanium_collected != b.titanium_collected:
                w = Team.A if a.titanium_collected > b.titanium_collected else Team.B
                return w, "titanium_collected"
            a_harv = sum(
                1
                for hid in self.harvesters
                if hid in self.entities and self.entities[hid].team is Team.A
            )
            b_harv = sum(
                1
                for hid in self.harvesters
                if hid in self.entities and self.entities[hid].team is Team.B
            )
            if a_harv != b_harv:
                w = Team.A if a_harv > b_harv else Team.B
                return w, "harvesters"
            if a.axionite != b.axionite:
                w = Team.A if a.axionite > b.axionite else Team.B
                return w, "axionite_stored"
            if a.titanium != b.titanium:
                w = Team.A if a.titanium > b.titanium else Team.B
                return w, "titanium_stored"
            w = Team.A if self.rng.random() < 0.5 else Team.B
            return w, "coinflip"
        return None, ""

    def _append_diff(self, diff: Diff) -> None:
        match diff:
            case DiffPlaceEntity(entity=entity):
                diff = DiffPlaceEntity(entity=copy.copy(entity))
            case DiffIndicatorLine() | DiffIndicatorDot():
                if self.suppress_indicators:
                    return
        self._current_diffs.append(diff)

    def new_turn(self) -> None:
        self._current_diffs = []
        self.replay_diffs.append(self._current_diffs)

    def apply_passive_income(self) -> None:
        if (self.turn + 1) % GameConstants.PASSIVE_TITANIUM_INTERVAL == 0:
            for p in self.players:
                p.titanium += GameConstants.PASSIVE_TITANIUM_AMOUNT

    def update_cooldowns(self) -> None:
        for uid in self.unit_order:
            e = self.entities.get(uid)
            if e is None:
                continue
            if not _is_unit(e):
                msg = f"unit_order contains non-unit id {uid}"
                raise RuntimeError(msg)
            match e:
                case (
                    BuilderBot()
                    | Core()
                    | Gunner()
                    | Sentinel()
                    | Breach()
                    | Launcher()
                ):
                    if e.action_cooldown > 0:
                        e.action_cooldown -= 1
                    if e.move_cooldown > 0:
                        e.move_cooldown -= 1

        for hid in self.harvesters:
            e = self.entities.get(hid)
            if e is None:
                continue
            if not isinstance(e, Harvester):
                msg = f"harvesters contains non-harvester id {hid}"
                raise TypeError(msg)
            if e.cooldown > 0:
                e.cooldown -= 1

    def move_builder_bot(self, bot_id: int, new_x: int, new_y: int) -> None:
        bot = self.entities.get(bot_id)
        assert bot is not None
        assert isinstance(bot, BuilderBot)
        fx, fy = bot.x, bot.y
        assert (fx, fy) != (new_x, new_y)
        assert self.in_bounds(fx, fy)
        assert self.in_bounds(new_x, new_y)
        assert self.is_tile_bot_passable(new_x, new_y, bot.team)
        self.tiles[new_y][new_x].bot = bot_id
        self.tiles[fy][fx].bot = None
        bot.x = new_x
        bot.y = new_y
        assert bot.move_cooldown == 0
        bot.move_cooldown = 1
        self._append_diff(DiffMove(id=bot_id, to_x=new_x, to_y=new_y))
        self._append_diff(DiffSetMoveCooldown(id=bot_id, value=1))

    def apply_damage(self, eid: int, amount: int) -> None:
        entity = self.entities.get(eid)
        assert entity is not None, f"unknown entity id {eid}"
        entity.hp -= amount
        self._append_diff(DiffUpdateHp(id=eid, delta=-amount))
        if entity.hp <= 0:
            self.destroy_entity(eid)

    def damage_tile(self, x: int, y: int, amount: int) -> None:
        if not self.in_bounds(x, y):
            return
        t = self.tiles[y][x]
        bid = t.building
        bot_id = t.bot
        if bid is not None:
            self.apply_damage(bid, amount)
        if bot_id is not None:
            self.apply_damage(bot_id, amount)

    def turret_damage_tile(self, x: int, y: int, amount: int) -> None:
        if not self.in_bounds(x, y):
            return
        t = self.tiles[y][x]
        bid = t.building
        bot_id = t.bot
        if bot_id is not None:
            self.apply_damage(bot_id, amount)
        elif bid is not None:
            self.apply_damage(bid, amount)

    def heal_tile(self, x: int, y: int, team: Team) -> None:
        assert self.in_bounds(x, y)
        t = self.tiles[y][x]
        ids: list[int] = []
        for eid in (t.building, t.bot):
            if eid is not None:
                e = self.entities.get(eid)
                if e is not None and e.team is team:
                    ids.append(eid)
        for eid in ids:
            e = self.entities[eid]
            heal = min(GameConstants.HEAL_AMOUNT, e.max_hp - e.hp)
            if heal > 0:
                e.hp += heal
                self._append_diff(DiffUpdateHp(id=eid, delta=heal))

    def remove_builder_bot(self, bot_id: int) -> None:
        bot = self.entities.pop(bot_id)
        assert isinstance(bot, BuilderBot)
        self.players[_TEAM_IDX[bot.team]].scale_milli -= 200
        x, y = bot.x, bot.y
        assert self.in_bounds(x, y)
        t = self.tiles[y][x]
        assert t.bot == bot_id
        t.bot = None
        self.unit_order = [u for u in self.unit_order if u != bot_id]
        self._append_diff(DiffRemove(id=bot_id))

    def remove_building(self, eid: int) -> None:
        building = self.entities.pop(eid)
        assert not isinstance(building, BuilderBot)
        self.players[_TEAM_IDX[building.team]].scale_milli -= scale_contribution(
            building,
        )
        if _is_unit(building):
            self.unit_order = [u for u in self.unit_order if u != eid]
        if isinstance(building, Harvester):
            self.harvesters = [h for h in self.harvesters if h != eid]
        x, y = building.x, building.y
        if isinstance(building, Core):
            for d in ALL_DIRS_AND_CENTRE:
                px, py_ = _pos_add(x, y, d)
                assert self.in_bounds(px, py_)
                t = self.tiles[py_][px]
                assert t.building == eid
                t.building = None
        else:
            assert self.in_bounds(x, y)
            self.tiles[y][x].building = None
        self._append_diff(DiffRemove(id=eid))

    def destroy_entity(self, eid: int) -> None:
        e = self.entities.get(eid)
        assert e is not None, f"unknown entity id {eid}"
        if isinstance(e, BuilderBot):
            self.remove_builder_bot(eid)
        else:
            self.remove_building(eid)

    def _destroy_marker_if_present(self, x: int, y: int) -> None:
        t = self.tiles[y][x]
        existing_id = t.building
        if existing_id is None:
            return
        e = self.entities.get(existing_id)
        if e is not None and isinstance(e, Marker):
            self.destroy_entity(existing_id)

    def _place_building_tile(self, eid: int, x: int, y: int) -> None:
        self.tiles[y][x].building = eid

    def _finish_building(self, bot_id: int, building: Entity) -> None:
        eid = building.id
        team = building.team
        assert eid not in self.entities
        self.players[_TEAM_IDX[team]].scale_milli += scale_contribution(building)
        self.entities[eid] = building
        if _is_unit(building):
            self.unit_order.append(eid)
        if isinstance(building, Harvester):
            self.harvesters.append(eid)
        bot = self.entities.get(bot_id)
        assert bot is not None
        assert isinstance(bot, BuilderBot)
        bot.action_cooldown += 1
        self._append_diff(DiffSetActionCooldown(id=bot_id, value=bot.action_cooldown))
        self._append_diff(DiffPlaceEntity(entity=building))

    def build_conveyor(self, bot_id: int, x: int, y: int, direction: Direction) -> int:
        team = self.entities[bot_id].team
        cost = self.scaled_cost(team, GameConstants.CONVEYOR_BASE_COST)
        self.spend(team, cost)
        self._destroy_marker_if_present(x, y)
        eid = self.new_id()
        self._place_building_tile(eid, x, y)
        building = Conveyor(
            id=eid,
            team=team,
            x=x,
            y=y,
            hp=GameConstants.CONVEYOR_MAX_HP,
            max_hp=GameConstants.CONVEYOR_MAX_HP,
            direction=direction,
        )
        self._finish_building(bot_id, building)
        return eid

    def build_splitter(self, bot_id: int, x: int, y: int, direction: Direction) -> int:
        team = self.entities[bot_id].team
        cost = self.scaled_cost(team, GameConstants.SPLITTER_BASE_COST)
        self.spend(team, cost)
        self._destroy_marker_if_present(x, y)
        eid = self.new_id()
        self._place_building_tile(eid, x, y)
        building = Splitter(
            id=eid,
            team=team,
            x=x,
            y=y,
            hp=GameConstants.SPLITTER_MAX_HP,
            max_hp=GameConstants.SPLITTER_MAX_HP,
            direction=direction,
        )
        self._finish_building(bot_id, building)
        return eid

    def build_bridge(
        self,
        bot_id: int,
        x: int,
        y: int,
        target_x: int,
        target_y: int,
    ) -> int:
        team = self.entities[bot_id].team
        cost = self.scaled_cost(team, GameConstants.BRIDGE_BASE_COST)
        self.spend(team, cost)
        self._destroy_marker_if_present(x, y)
        eid = self.new_id()
        self._place_building_tile(eid, x, y)
        building = Bridge(
            id=eid,
            team=team,
            x=x,
            y=y,
            hp=GameConstants.BRIDGE_MAX_HP,
            max_hp=GameConstants.BRIDGE_MAX_HP,
            target_x=target_x,
            target_y=target_y,
        )
        self._finish_building(bot_id, building)
        return eid

    def build_armoured_conveyor(
        self,
        bot_id: int,
        x: int,
        y: int,
        direction: Direction,
    ) -> int:
        team = self.entities[bot_id].team
        cost = self.scaled_cost(team, GameConstants.ARMOURED_CONVEYOR_BASE_COST)
        self.spend(team, cost)
        self._destroy_marker_if_present(x, y)
        eid = self.new_id()
        self._place_building_tile(eid, x, y)
        building = ArmouredConveyor(
            id=eid,
            team=team,
            x=x,
            y=y,
            hp=GameConstants.ARMOURED_CONVEYOR_MAX_HP,
            max_hp=GameConstants.ARMOURED_CONVEYOR_MAX_HP,
            direction=direction,
        )
        self._finish_building(bot_id, building)
        return eid

    def build_harvester(self, bot_id: int, x: int, y: int) -> int:
        team = self.entities[bot_id].team
        cost = self.scaled_cost(team, GameConstants.HARVESTER_BASE_COST)
        self.spend(team, cost)
        self._destroy_marker_if_present(x, y)
        eid = self.new_id()
        self._place_building_tile(eid, x, y)
        env = self.tiles[y][x].env
        if env is Environment.ORE_TITANIUM:
            resource_type = ResourceType.TITANIUM
        elif env is Environment.ORE_AXIONITE:
            resource_type = ResourceType.RAW_AXIONITE
        else:
            msg = f"build_harvester on non-ore tile ({x},{y}): env={env}"
            raise RuntimeError(msg)
        building = Harvester(
            id=eid,
            team=team,
            x=x,
            y=y,
            hp=GameConstants.HARVESTER_MAX_HP,
            max_hp=GameConstants.HARVESTER_MAX_HP,
            resource_type=resource_type,
        )
        self._finish_building(bot_id, building)
        return eid

    def build_road(self, bot_id: int, x: int, y: int) -> int:
        team = self.entities[bot_id].team
        cost = self.scaled_cost(team, GameConstants.ROAD_BASE_COST)
        self.spend(team, cost)
        self._destroy_marker_if_present(x, y)
        eid = self.new_id()
        self._place_building_tile(eid, x, y)
        building = Road(
            id=eid,
            team=team,
            x=x,
            y=y,
            hp=GameConstants.ROAD_MAX_HP,
            max_hp=GameConstants.ROAD_MAX_HP,
        )
        self._finish_building(bot_id, building)
        return eid

    def build_barrier(self, bot_id: int, x: int, y: int) -> int:
        team = self.entities[bot_id].team
        cost = self.scaled_cost(team, GameConstants.BARRIER_BASE_COST)
        self.spend(team, cost)
        self._destroy_marker_if_present(x, y)
        eid = self.new_id()
        self._place_building_tile(eid, x, y)
        building = Barrier(
            id=eid,
            team=team,
            x=x,
            y=y,
            hp=GameConstants.BARRIER_MAX_HP,
            max_hp=GameConstants.BARRIER_MAX_HP,
        )
        self._finish_building(bot_id, building)
        return eid

    def build_gunner(self, bot_id: int, x: int, y: int, direction: Direction) -> int:
        team = self.entities[bot_id].team
        cost = self.scaled_cost(team, GameConstants.GUNNER_BASE_COST)
        self.spend(team, cost)
        self._destroy_marker_if_present(x, y)
        eid = self.new_id()
        self._place_building_tile(eid, x, y)
        building = Gunner(
            id=eid,
            team=team,
            x=x,
            y=y,
            hp=GameConstants.GUNNER_MAX_HP,
            max_hp=GameConstants.GUNNER_MAX_HP,
            direction=direction,
        )
        self._finish_building(bot_id, building)
        return eid

    def build_sentinel(self, bot_id: int, x: int, y: int, direction: Direction) -> int:
        team = self.entities[bot_id].team
        cost = self.scaled_cost(team, GameConstants.SENTINEL_BASE_COST)
        self.spend(team, cost)
        self._destroy_marker_if_present(x, y)
        eid = self.new_id()
        self._place_building_tile(eid, x, y)
        building = Sentinel(
            id=eid,
            team=team,
            x=x,
            y=y,
            hp=GameConstants.SENTINEL_MAX_HP,
            max_hp=GameConstants.SENTINEL_MAX_HP,
            direction=direction,
        )
        self._finish_building(bot_id, building)
        return eid

    def build_breach(self, bot_id: int, x: int, y: int, direction: Direction) -> int:
        team = self.entities[bot_id].team
        cost = self.scaled_cost(team, GameConstants.BREACH_BASE_COST)
        self.spend(team, cost)
        self._destroy_marker_if_present(x, y)
        eid = self.new_id()
        self._place_building_tile(eid, x, y)
        building = Breach(
            id=eid,
            team=team,
            x=x,
            y=y,
            hp=GameConstants.BREACH_MAX_HP,
            max_hp=GameConstants.BREACH_MAX_HP,
            direction=direction,
        )
        self._finish_building(bot_id, building)
        return eid

    def build_launcher(self, bot_id: int, x: int, y: int) -> int:
        team = self.entities[bot_id].team
        cost = self.scaled_cost(team, GameConstants.LAUNCHER_BASE_COST)
        self.spend(team, cost)
        self._destroy_marker_if_present(x, y)
        eid = self.new_id()
        self._place_building_tile(eid, x, y)
        building = Launcher(
            id=eid,
            team=team,
            x=x,
            y=y,
            hp=GameConstants.LAUNCHER_MAX_HP,
            max_hp=GameConstants.LAUNCHER_MAX_HP,
        )
        self._finish_building(bot_id, building)
        return eid

    def build_foundry(self, bot_id: int, x: int, y: int) -> int:
        team = self.entities[bot_id].team
        cost = self.scaled_cost(team, GameConstants.FOUNDRY_BASE_COST)
        self.spend(team, cost)
        self._destroy_marker_if_present(x, y)
        eid = self.new_id()
        self._place_building_tile(eid, x, y)
        building = Foundry(
            id=eid,
            team=team,
            x=x,
            y=y,
            hp=GameConstants.FOUNDRY_MAX_HP,
            max_hp=GameConstants.FOUNDRY_MAX_HP,
        )
        self._finish_building(bot_id, building)
        return eid

    def place_marker(self, team: Team, x: int, y: int, value: int) -> None:
        assert self.in_bounds(x, y)
        t = self.tiles[y][x]
        bid = t.building
        if bid is not None:
            e = self.entities.get(bid)
            assert e is not None
            if isinstance(e, Marker) and e.team is team:
                e.value = value
                self._append_diff(DiffPlaceEntity(entity=e))
                return
            msg = f"marker placed on non-marker or enemy building id {bid}"
            raise RuntimeError(msg)
        eid = self.new_id()
        self._place_building_tile(eid, x, y)
        building = Marker(
            id=eid,
            team=team,
            x=x,
            y=y,
            hp=GameConstants.MARKER_MAX_HP,
            max_hp=GameConstants.MARKER_MAX_HP,
            value=value,
        )
        self.entities[eid] = building
        self._append_diff(DiffPlaceEntity(entity=building))

    def spawn_builder(self, core_id: int, x: int, y: int) -> int:
        core = self.entities.get(core_id)
        assert core is not None
        assert isinstance(core, Core)
        team = core.team
        assert self.in_bounds(x, y)
        cost = self.scaled_cost(team, GameConstants.BUILDER_BOT_BASE_COST)
        self.spend(team, cost)
        eid = self.new_id()
        bot = BuilderBot(
            id=eid,
            team=team,
            x=x,
            y=y,
            hp=GameConstants.BUILDER_BOT_MAX_HP,
            max_hp=GameConstants.BUILDER_BOT_MAX_HP,
        )
        self.entities[eid] = bot
        self.players[_TEAM_IDX[team]].scale_milli += 200
        t = self.tiles[y][x]
        assert t.bot is None
        t.bot = eid
        self.unit_order.append(eid)
        self._append_diff(DiffPlaceEntity(entity=bot))
        core.action_cooldown = 1
        self._append_diff(DiffSetActionCooldown(id=core_id, value=1))
        return eid

    def gunner_target(self, turret_id: int) -> tuple[int, int] | None:
        e = self.entities[turret_id]
        assert isinstance(e, Gunner)
        ox, oy = e.x, e.y
        d = e.direction
        dx, dy = d.delta()
        px, py_ = ox + dx, oy + dy
        while True:
            if not self.in_bounds(px, py_):
                return None
            if (
                _distance_squared(ox, oy, px, py_)
                > GameConstants.GUNNER_VISION_RADIUS_SQ
            ):
                return None
            t = self.tiles[py_][px]
            if t.env is Environment.WALL:
                return (px, py_)
            if t.bot is not None:
                return (px, py_)
            bid = t.building
            if bid is not None:
                be = self.entities.get(bid)
                if be is not None and not isinstance(be, Marker):
                    return (px, py_)
            px += dx
            py_ += dy

    def gunner_attackable_tiles(
        self,
        ox: int,
        oy: int,
        direction: Direction,
    ) -> list[tuple[int, int]]:
        dx, dy = direction.delta()
        result: list[tuple[int, int]] = []
        px, py_ = ox + dx, oy + dy
        while True:
            if not self.in_bounds(px, py_):
                break
            if (
                _distance_squared(ox, oy, px, py_)
                > GameConstants.GUNNER_VISION_RADIUS_SQ
            ):
                break
            result.append((px, py_))
            px += dx
            py_ += dy
        return result

    def sentinel_attackable_tiles(
        self,
        ox: int,
        oy: int,
        direction: Direction,
    ) -> list[tuple[int, int]]:
        dx, dy = direction.delta()
        result: list[tuple[int, int]] = []
        seen: set[tuple[int, int]] = set()
        k = 1
        while k * k * (dx * dx + dy * dy) <= GameConstants.SENTINEL_VISION_RADIUS_SQ:
            for ly in range(-1, 2):
                for lx in range(-1, 2):
                    px = ox + k * dx + lx
                    py_ = oy + k * dy + ly
                    if self.in_bounds(px, py_):
                        dsq = _distance_squared(ox, oy, px, py_)
                        if (
                            dsq > 0
                            and dsq <= GameConstants.SENTINEL_VISION_RADIUS_SQ
                            and (px, py_) not in seen
                        ):
                            seen.add((px, py_))
                            result.append((px, py_))
            k += 1
        result.sort()
        return result

    def breach_attackable_tiles(
        self,
        ox: int,
        oy: int,
        direction: Direction,
    ) -> list[tuple[int, int]]:
        dx, dy = direction.delta()
        r = math.ceil(math.sqrt(GameConstants.BREACH_ATTACK_RADIUS_SQ))
        result: list[tuple[int, int]] = []
        for ry in range(-r, r + 1):
            for rx in range(-r, r + 1):
                dsq = rx * rx + ry * ry
                if dsq == 0 or dsq > GameConstants.BREACH_ATTACK_RADIUS_SQ:
                    continue
                dot = rx * dx + ry * dy
                if dot < 0:
                    continue
                px = ox + rx
                py_ = oy + ry
                if self.in_bounds(px, py_):
                    result.append((px, py_))
        return result

    def sentinel_target_valid(self, turret_id: int, tx: int, ty: int) -> bool:
        e = self.entities[turret_id]
        assert isinstance(e, Sentinel)
        ox, oy = e.x, e.y
        dsq = _distance_squared(ox, oy, tx, ty)
        if dsq == 0 or dsq > GameConstants.SENTINEL_VISION_RADIUS_SQ:
            return False
        dx, dy = e.direction.delta()
        rx = tx - ox
        ry = ty - oy
        k = 1
        while k * k * (dx * dx + dy * dy) <= GameConstants.SENTINEL_VISION_RADIUS_SQ:
            lx = rx - k * dx
            ly = ry - k * dy
            if abs(lx) <= 1 and abs(ly) <= 1:
                return True
            k += 1
        return False

    def breach_target_valid(self, turret_id: int, tx: int, ty: int) -> bool:
        e = self.entities[turret_id]
        assert isinstance(e, Breach)
        ox, oy = e.x, e.y
        dsq = _distance_squared(ox, oy, tx, ty)
        if dsq == 0 or dsq > GameConstants.BREACH_ATTACK_RADIUS_SQ:
            return False
        dx, dy = e.direction.delta()
        rx = tx - ox
        ry = ty - oy
        dot = rx * dx + ry * dy
        return dot >= 0

    def launcher_target_valid(self, turret_id: int, tx: int, ty: int) -> bool:
        e = self.entities[turret_id]
        ox, oy = e.x, e.y
        dsq = _distance_squared(ox, oy, tx, ty)
        return dsq > 0 and dsq <= GameConstants.LAUNCHER_VISION_RADIUS_SQ

    def fire_gunner(self, turret_id: int, *, axionite: bool) -> None:
        damage = (
            GameConstants.GUNNER_AXIONITE_DAMAGE
            if axionite
            else GameConstants.GUNNER_DAMAGE
        )
        e = self.entities[turret_id]
        assert isinstance(e, Gunner)
        from_x, from_y = e.x, e.y
        target = self.gunner_target(turret_id)
        if target is not None:
            self.turret_damage_tile(target[0], target[1], damage)
            self._append_diff(
                DiffFireTurret(
                    from_x=from_x,
                    from_y=from_y,
                    to_x=target[0],
                    to_y=target[1],
                ),
            )
        self._finish_firing_turret(
            turret_id,
            GameConstants.GUNNER_AMMO_COST,
            GameConstants.GUNNER_FIRE_COOLDOWN,
        )

    def fire_sentinel(
        self,
        turret_id: int,
        tx: int,
        ty: int,
        *,
        axionite: bool,
    ) -> None:
        e = self.entities[turret_id]
        assert isinstance(e, Sentinel)
        from_x, from_y = e.x, e.y
        self._append_diff(
            DiffFireTurret(
                from_x=from_x,
                from_y=from_y,
                to_x=tx,
                to_y=ty,
            ),
        )
        self.turret_damage_tile(tx, ty, GameConstants.SENTINEL_DAMAGE)
        if axionite and self.in_bounds(tx, ty):
            t = self.tiles[ty][tx]
            ids: list[int] = [eid for eid in (t.building, t.bot) if eid is not None]
            for eid in ids:
                entity = self.entities.get(eid)
                if entity is None:
                    continue
                if _is_unit(entity):
                    match entity:
                        case (
                            BuilderBot()
                            | Core()
                            | Gunner()
                            | Sentinel()
                            | Breach()
                            | Launcher()
                        ):
                            entity.action_cooldown += (
                                GameConstants.SENTINEL_STUN_DURATION
                            )
                            entity.move_cooldown += GameConstants.SENTINEL_STUN_DURATION
                            self._append_diff(
                                DiffSetActionCooldown(
                                    id=eid,
                                    value=entity.action_cooldown,
                                ),
                            )
                            self._append_diff(
                                DiffSetMoveCooldown(
                                    id=eid,
                                    value=entity.move_cooldown,
                                ),
                            )
        self._finish_firing_turret(
            turret_id,
            GameConstants.SENTINEL_AMMO_COST,
            GameConstants.SENTINEL_FIRE_COOLDOWN,
        )

    def fire_breach(self, turret_id: int, tx: int, ty: int) -> None:
        e = self.entities[turret_id]
        assert isinstance(e, Breach)
        ox, oy = e.x, e.y
        self._append_diff(DiffFireTurret(from_x=ox, from_y=oy, to_x=tx, to_y=ty))
        self.turret_damage_tile(tx, ty, GameConstants.BREACH_DAMAGE)
        for d in ALL_DIRS:
            sx, sy = _pos_add(tx, ty, d)
            if sx == ox and sy == oy:
                continue
            self.damage_tile(sx, sy, GameConstants.BREACH_SPLASH_DAMAGE)
        self._finish_firing_turret(
            turret_id,
            GameConstants.BREACH_AMMO_COST,
            GameConstants.BREACH_FIRE_COOLDOWN,
        )

    def fire_launcher(self, turret_id: int, bot_id: int, tx: int, ty: int) -> None:
        bot = self.entities[bot_id]
        assert isinstance(bot, BuilderBot)
        fx, fy = bot.x, bot.y
        self.tiles[fy][fx].bot = None
        self.tiles[ty][tx].bot = bot_id
        bot.x = tx
        bot.y = ty
        self._append_diff(DiffMove(id=bot_id, to_x=tx, to_y=ty))
        self._finish_firing_turret(turret_id, 0, GameConstants.LAUNCHER_FIRE_COOLDOWN)

    def _finish_firing_turret(
        self,
        turret_id: int,
        ammo_cost: int,
        cooldown: int,
    ) -> None:
        e = self.entities.get(turret_id)
        if e is None:
            return
        match e:
            case Gunner() | Sentinel() | Breach() | Launcher():
                e.ammo_amount -= ammo_cost
                assert e.ammo_amount >= 0
                if e.ammo_amount == 0:
                    e.ammo_type = None
                e.action_cooldown += cooldown
                self._append_diff(
                    DiffSetActionCooldown(id=turret_id, value=e.action_cooldown),
                )

    def rotate_gunner(self, gunner_id: int, direction: Direction) -> None:
        e = self.entities[gunner_id]
        assert isinstance(e, Gunner)
        team = e.team
        self.spend(team, GameConstants.GUNNER_ROTATE_COST)
        e.direction = direction
        e.action_cooldown += GameConstants.GUNNER_ROTATE_COOLDOWN
        self._append_diff(DiffPlaceEntity(entity=e))
        self._append_diff(DiffSetActionCooldown(id=gunner_id, value=e.action_cooldown))

    def builder_bot_attack(self, bot_id: int, building_id: int) -> None:
        bot = self.entities[bot_id]
        assert isinstance(bot, BuilderBot)
        team = bot.team
        self.spend(team, GameConstants.BUILDER_BOT_ATTACK_COST)
        self.apply_damage(building_id, GameConstants.BUILDER_BOT_ATTACK_DAMAGE)
        self._append_diff(DiffBuilderBotAttack(id=bot_id))
        bot_e = self.entities.get(bot_id)
        if bot_e is not None:
            assert isinstance(bot_e, BuilderBot)
            bot_e.action_cooldown += 1
            self._append_diff(
                DiffSetActionCooldown(id=bot_id, value=bot_e.action_cooldown),
            )

    def convert(self, team: Team, amount: int) -> None:
        ti = _TEAM_IDX[team]
        ti_gain = amount * GameConstants.AXIONITE_CONVERSION_TITANIUM_RATE
        self.players[ti].axionite -= amount
        self.players[ti].axionite_collected -= amount
        self.players[ti].titanium += ti_gain
        self.players[ti].titanium_collected += ti_gain

    def _resource_to_feed(self, e: Entity) -> ResourceType | None:
        match e:
            case (
                Conveyor(stored=stored)
                | Splitter(stored=stored)
                | ArmouredConveyor(stored=stored)
                | Bridge(stored=stored)
            ):
                return stored
            case Harvester(cooldown=cd, resource_type=rt):
                if cd == 0:
                    return rt
                return None
            case Foundry(stored=stored):
                if stored is ResourceType.REFINED_AXIONITE:
                    return ResourceType.REFINED_AXIONITE
                return None
            case _:
                return None

    def _resource_to_feed_id(self, e: Entity) -> int | None:
        match e:
            case (
                Conveyor(stored_id=sid)
                | Splitter(stored_id=sid)
                | ArmouredConveyor(stored_id=sid)
                | Bridge(stored_id=sid)
            ):
                return sid
            case Harvester():
                return None
            case Foundry(stored=stored, stored_id=sid):
                if stored is ResourceType.REFINED_AXIONITE:
                    return sid
                return None
            case _:
                return None

    def _output_targets(self, e: Entity) -> list[tuple[int, int]]:
        ex, ey = e.x, e.y
        match e:
            case Conveyor(direction=d) | ArmouredConveyor(direction=d):
                return [_pos_add(ex, ey, d)]
            case Bridge(target_x=tx, target_y=ty):
                return [(tx, ty)]
            case Splitter(direction=d):
                excluded = d.opposite()
                return [
                    _pos_add(ex, ey, dd) for dd in CARDINAL_DIRS if dd is not excluded
                ]
            case Harvester() | Foundry():
                return [_pos_add(ex, ey, d) for d in CARDINAL_DIRS]
            case _:
                return []

    def _can_accept_from(
        self,
        sink: Entity,
        resource: ResourceType,
        source_x: int,
        source_y: int,
        *,
        source_is_bridge: bool,
    ) -> bool:
        sx, sy = sink.x, sink.y
        match sink:
            case Conveyor(direction=d, stored=stored):
                out_x, out_y = _pos_add(sx, sy, d)
                if not source_is_bridge and source_x == out_x and source_y == out_y:
                    return False
                return stored is None
            case Splitter(direction=d, stored=stored):
                inp_dir = d.opposite()
                inp_x, inp_y = _pos_add(sx, sy, inp_dir)
                if not source_is_bridge and (source_x != inp_x or source_y != inp_y):
                    return False
                return stored is None
            case ArmouredConveyor(direction=d, stored=stored):
                out_x, out_y = _pos_add(sx, sy, d)
                if not source_is_bridge and source_x == out_x and source_y == out_y:
                    return False
                return stored is None
            case Bridge(stored=stored):
                return stored is None
            case Foundry(stored=stored):
                if resource is ResourceType.TITANIUM and stored in (
                    None,
                    ResourceType.RAW_AXIONITE,
                ):
                    return True
                return bool(
                    resource is ResourceType.RAW_AXIONITE
                    and stored in (None, ResourceType.TITANIUM),
                )
            case Core():
                return True
            case Gunner(ammo_amount=aa, direction=d):
                if aa != 0:
                    return False
                out_x, out_y = _pos_add(sx, sy, d)
                return not (
                    not source_is_bridge and source_x == out_x and source_y == out_y
                )
            case Sentinel(ammo_amount=aa, direction=d):
                if aa != 0:
                    return False
                out_x, out_y = _pos_add(sx, sy, d)
                return not (
                    not source_is_bridge and source_x == out_x and source_y == out_y
                )
            case Breach(ammo_amount=aa, direction=d):
                if aa != 0:
                    return False
                if resource is not ResourceType.REFINED_AXIONITE:
                    return False
                out_x, out_y = _pos_add(sx, sy, d)
                return not (
                    not source_is_bridge and source_x == out_x and source_y == out_y
                )
            case _:
                return False

    def _receive_resource(
        self,
        sink: Entity,
        resource: ResourceType,
        resource_id: int,
    ) -> None:
        match sink:
            case Conveyor() | Splitter() | ArmouredConveyor() | Bridge():
                sink.stored = resource
                sink.stored_id = resource_id
            case Core():
                if resource is not ResourceType.RAW_AXIONITE:
                    sink.received.append(resource)
            case Gunner() | Sentinel():
                if resource is not ResourceType.RAW_AXIONITE:
                    self._receive_ammo(sink, resource)
            case Breach():
                self._receive_ammo(sink, resource)
            case Foundry():
                stored = sink.stored
                if stored is None:
                    if resource in (ResourceType.TITANIUM, ResourceType.RAW_AXIONITE):
                        sink.stored = resource
                        sink.stored_id = resource_id
                elif (
                    resource is ResourceType.TITANIUM
                    and stored is ResourceType.RAW_AXIONITE
                ) or (
                    resource is ResourceType.RAW_AXIONITE
                    and stored is ResourceType.TITANIUM
                ):
                    sink.stored = ResourceType.REFINED_AXIONITE
                    sink.stored_id = resource_id

    def _receive_ammo(
        self,
        turret: Gunner | Sentinel | Breach,
        resource: ResourceType,
    ) -> None:
        assert turret.ammo_amount == 0
        if resource is ResourceType.REFINED_AXIONITE:
            turret.ammo_type = ResourceType.REFINED_AXIONITE
        else:
            turret.ammo_type = ResourceType.TITANIUM
        turret.ammo_amount = GameConstants.STACK_SIZE

    def _consume_feed(self, source: Entity) -> None:
        match source:
            case Conveyor() | Splitter() | ArmouredConveyor() | Bridge() | Foundry():
                source.stored = None
                source.stored_id = None
            case Harvester():
                source.cooldown = 4

    def _has_no_output(self, e: Entity) -> bool:
        match e:
            case (
                Conveyor(stored=stored)
                | Splitter(stored=stored)
                | ArmouredConveyor(stored=stored)
                | Bridge(stored=stored)
            ):
                return stored is None
            case Foundry(stored=stored):
                return stored in (
                    None,
                    ResourceType.TITANIUM,
                    ResourceType.RAW_AXIONITE,
                )
            case _:
                return False

    def distribute_resources(self) -> None:
        incoming: dict[tuple[int, int], list[tuple[int, int]]] = {}
        outgoing_count: dict[tuple[int, int], int] = {}
        processed: set[tuple[int, int]] = set()

        for row in self.tiles:
            for tile in row:
                bid = tile.building
                if bid is None:
                    continue
                entity = self.entities.get(bid)
                if entity is None:
                    continue
                epos = (entity.x, entity.y)
                if self._has_no_output(entity):
                    processed.add(epos)
                count = 0
                for sx, sy in self._output_targets(entity):
                    if not self.in_bounds(sx, sy):
                        continue
                    st = self.tiles[sy][sx]
                    if st.building is not None:
                        count += 1
                        incoming.setdefault((sx, sy), []).append(epos)
                outgoing_count[epos] = count

        def edge_priority(src: tuple[int, int], snk: tuple[int, int]) -> int:
            src_out = outgoing_count.get(src, 0)
            snk_in = len(incoming.get(snk, []))
            if src_out == 1 and snk_in == 1:
                return 2**31 - 1
            return -self.edge_last_used.get((src[0], src[1], snk[0], snk[1]), 0)

        heap: list[tuple[float, int, int, int, int, int]] = []
        counter = 0
        for sink_pos, sources in sorted(incoming.items()):
            sink_id = self.tiles[sink_pos[1]][sink_pos[0]].building
            if sink_id is None:
                continue
            for source_pos in sources:
                source_id = self.tiles[source_pos[1]][source_pos[0]].building
                if source_id is None:
                    continue
                source = self.entities.get(source_id)
                if source is None:
                    continue
                resource = self._resource_to_feed(source)
                if resource is None:
                    continue
                sink = self.entities.get(sink_id)
                if sink is None:
                    continue
                src_is_bridge = isinstance(source, Bridge)
                if not self._can_accept_from(
                    sink,
                    resource,
                    source_pos[0],
                    source_pos[1],
                    source_is_bridge=src_is_bridge,
                ):
                    continue
                pri = edge_priority(source_pos, sink_pos)
                jitter = self.rng.random()
                heapq.heappush(
                    heap,
                    (
                        -(pri + jitter),
                        counter,
                        source_pos[0],
                        source_pos[1],
                        sink_pos[0],
                        sink_pos[1],
                    ),
                )
                counter += 1

        moves: list[tuple[int, int, int, int, int]] = []

        while heap:
            _, _, sx, sy, kx, ky = heapq.heappop(heap)
            source_pos = (sx, sy)
            sink_pos = (kx, ky)
            if source_pos in processed:
                continue
            source_id = self.tiles[sy][sx].building
            sink_id = self.tiles[ky][kx].building
            if source_id is None or sink_id is None:
                continue
            source = self.entities.get(source_id)
            if source is None:
                continue
            resource = self._resource_to_feed(source)
            if resource is None:
                continue
            sink = self.entities.get(sink_id)
            if sink is None:
                continue
            src_is_bridge = isinstance(source, Bridge)
            if not self._can_accept_from(
                sink,
                resource,
                sx,
                sy,
                source_is_bridge=src_is_bridge,
            ):
                continue

            resource_id = self._resource_to_feed_id(source)
            if resource_id is None:
                self.next_id += 1
                resource_id = self.next_id

            self._receive_resource(sink, resource, resource_id)
            self._consume_feed(source)
            moves.append((sx, sy, kx, ky, resource_id))
            processed.add(source_pos)

            for upstream_pos in incoming.get(source_pos, []):
                if upstream_pos in processed:
                    continue
                upstream_id = self.tiles[upstream_pos[1]][upstream_pos[0]].building
                if upstream_id is None:
                    continue
                upstream = self.entities.get(upstream_id)
                if upstream is None:
                    continue
                up_resource = self._resource_to_feed(upstream)
                if up_resource is None:
                    continue
                source_now = self.entities.get(source_id)
                if source_now is None:
                    continue
                up_is_bridge = isinstance(upstream, Bridge)
                if self._can_accept_from(
                    source_now,
                    up_resource,
                    upstream_pos[0],
                    upstream_pos[1],
                    source_is_bridge=up_is_bridge,
                ):
                    pri = edge_priority(upstream_pos, source_pos)
                    jitter = self.rng.random()
                    heapq.heappush(
                        heap,
                        (
                            -(pri + jitter),
                            counter,
                            upstream_pos[0],
                            upstream_pos[1],
                            source_pos[0],
                            source_pos[1],
                        ),
                    )
                    counter += 1

        for e in self.entities.values():
            match e:
                case Core(team=team, received=received):
                    for resource in received:
                        self._add_resource(team, resource)
                    e.received = []

        for sx, sy, kx, ky, _ in moves:
            self.edge_last_used[(sx, sy, kx, ky)] = self.turn

        if moves:
            self._append_diff(DiffDistribute(moves=moves))

    def _add_resource(self, team: Team, resource: ResourceType) -> None:
        ti = _TEAM_IDX[team]
        p = self.players[ti]
        if resource is ResourceType.TITANIUM:
            p.titanium += GameConstants.STACK_SIZE
            p.resources_collected += GameConstants.STACK_SIZE
            p.titanium_collected += GameConstants.STACK_SIZE
        elif resource is ResourceType.REFINED_AXIONITE:
            p.axionite += GameConstants.STACK_SIZE
            p.resources_collected += GameConstants.STACK_SIZE
            p.axionite_collected += GameConstants.STACK_SIZE

    def launch_bot(
        self,
        launcher_id: int,
        bot_x: int,
        bot_y: int,
        target_x: int,
        target_y: int,
    ) -> None:
        bot_id = self.tiles[bot_y][bot_x].bot
        assert bot_id is not None
        self.fire_launcher(launcher_id, bot_id, target_x, target_y)

    def build_replay(self, winner: Team | None) -> pb.Replay:
        proto_map = _build_proto_map(self._environment, self._cores_init)

        turns: list[pb.Turn] = []
        for diff_list in self.replay_diffs:
            turn = pb.Turn()
            for diff in diff_list:
                update = _diff_to_proto(diff)
                if update is not None:
                    turn.updates.append(update)
            turns.append(turn)

        replay = pb.Replay()
        replay.map.CopyFrom(proto_map)
        replay.turns.extend(turns)
        if winner is not None:
            replay.winner = _team_to_proto(winner)
        return replay

    def write_replay(self, path: str, winner: Team | None) -> None:
        replay = self.build_replay(winner)
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(replay.SerializeToString())


_TEAM_TO_PB: dict[Team, pb.Team] = {
    Team.A: pb.Team.TEAM_A,
    Team.B: pb.Team.TEAM_B,
}

_DIR_TO_PB: dict[Direction, pb.Direction] = {
    Direction.CENTRE: pb.Direction.DIR_CENTRE,
    Direction.NORTH: pb.Direction.DIR_NORTH,
    Direction.NORTHEAST: pb.Direction.DIR_NORTHEAST,
    Direction.EAST: pb.Direction.DIR_EAST,
    Direction.SOUTHEAST: pb.Direction.DIR_SOUTHEAST,
    Direction.SOUTH: pb.Direction.DIR_SOUTH,
    Direction.SOUTHWEST: pb.Direction.DIR_SOUTHWEST,
    Direction.WEST: pb.Direction.DIR_WEST,
    Direction.NORTHWEST: pb.Direction.DIR_NORTHWEST,
}

_RESOURCE_TO_PB: dict[ResourceType | None, pb.ResourceType] = {
    None: pb.ResourceType.RESOURCE_NONE,
    ResourceType.TITANIUM: pb.ResourceType.RESOURCE_TITANIUM,
    ResourceType.RAW_AXIONITE: pb.ResourceType.RESOURCE_RAW_AXIONITE,
    ResourceType.REFINED_AXIONITE: pb.ResourceType.RESOURCE_REFINED_AXIONITE,
}


def _team_to_proto(team: Team) -> pb.Team:
    return _TEAM_TO_PB[team]


def _dir_to_proto(direction: Direction) -> pb.Direction:
    return _DIR_TO_PB[direction]


def _resource_to_proto(resource: ResourceType | None) -> pb.ResourceType:
    return _RESOURCE_TO_PB[resource]


def _build_proto_map(
    environment: list[list[int]],
    cores: list[tuple[int, int, int]],
) -> pb.Map:
    height = len(environment)
    width = len(environment[0]) if height > 0 else 0
    proto_map = pb.Map()
    proto_map.width = width
    proto_map.height = height
    for row in environment:
        tr = pb.TileRow()
        tr.tiles.extend(cast("list[pb.Environment]", row))
        proto_map.rows.append(tr)
    for idx, (cx, cy, team_idx) in enumerate(cores):
        cp = pb.CorePosition()
        cp.id = idx + 1
        cp.team = _TEAM_TO_PB[_IDX_TEAM[team_idx]]
        cp.position.x = cx
        cp.position.y = cy
        proto_map.cores.append(cp)
    return proto_map


def _entity_to_proto(entity: Entity) -> pb.Entity:
    pe = pb.Entity()
    pe.id = entity.id
    pe.team = _team_to_proto(entity.team)
    pe.position.x = entity.x
    pe.position.y = entity.y
    pe.hp = entity.hp
    pe.max_hp = entity.max_hp

    match entity:
        case BuilderBot(action_cooldown=ac, move_cooldown=mc):
            pe.builder_bot.CopyFrom(pb.BuilderBot(action_cooldown=ac, move_cooldown=mc))
        case Conveyor(direction=d, stored=s):
            pe.conveyor.CopyFrom(
                pb.Conveyor(direction=_dir_to_proto(d), stored=_resource_to_proto(s)),
            )
        case Splitter(direction=d, stored=s):
            pe.splitter.CopyFrom(
                pb.Splitter(direction=_dir_to_proto(d), stored=_resource_to_proto(s)),
            )
        case ArmouredConveyor(direction=d, stored=s):
            pe.armoured_conveyor.CopyFrom(
                pb.ArmouredConveyor(
                    direction=_dir_to_proto(d),
                    stored=_resource_to_proto(s),
                ),
            )
        case Bridge(target_x=tx, target_y=ty, stored=s):
            pe.bridge.CopyFrom(
                pb.Bridge(target=pb.Pos(x=tx, y=ty), stored=_resource_to_proto(s)),
            )
        case Harvester(cooldown=cd, resource_type=rt):
            pe.harvester.CopyFrom(
                pb.Harvester(cooldown=cd, resource_type=_resource_to_proto(rt)),
            )
        case Foundry(stored=s):
            pe.foundry.CopyFrom(pb.Foundry(stored=_resource_to_proto(s)))
        case Road():
            pe.road.CopyFrom(pb.Road())
        case Barrier():
            pe.barrier.CopyFrom(pb.Barrier())
        case Marker(value=v):
            pe.marker.CopyFrom(pb.Marker(value=v))
        case Core(action_cooldown=ac):
            pe.core.CopyFrom(pb.Core(action_cooldown=ac))
        case Gunner(direction=d, ammo_type=at, ammo_amount=aa):
            pe.gunner.CopyFrom(
                pb.Gunner(
                    direction=_dir_to_proto(d),
                    ammo_type=_resource_to_proto(at),
                    ammo_amount=aa,
                ),
            )
        case Sentinel(direction=d, ammo_type=at, ammo_amount=aa):
            pe.sentinel.CopyFrom(
                pb.Sentinel(
                    direction=_dir_to_proto(d),
                    ammo_type=_resource_to_proto(at),
                    ammo_amount=aa,
                ),
            )
        case Breach(direction=d, ammo_type=at, ammo_amount=aa):
            pe.breach.CopyFrom(
                pb.Breach(
                    direction=_dir_to_proto(d),
                    ammo_type=_resource_to_proto(at),
                    ammo_amount=aa,
                ),
            )
        case Launcher(ammo_type=at, ammo_amount=aa):
            pe.launcher.CopyFrom(
                pb.Launcher(ammo_type=_resource_to_proto(at), ammo_amount=aa),
            )
    return pe


def _diff_to_proto(diff: Diff) -> pb.Update | None:
    u = pb.Update()

    match diff:
        case DiffPlaceEntity(entity=entity):
            pe = _entity_to_proto(entity)
            u.place_entity.entity.CopyFrom(pe)
        case DiffMove(id=eid, to_x=tx, to_y=ty):
            u.move_builder_bot.id = eid
            u.move_builder_bot.to.x = tx
            u.move_builder_bot.to.y = ty
        case DiffRemove(id=eid):
            u.remove_entity.id = eid
        case DiffDistribute(moves=moves):
            for sx, sy, kx, ky, rid in moves:
                rm = pb.ResourceMove()
                getattr(rm, "from").x = sx
                getattr(rm, "from").y = sy
                rm.to.x = kx
                rm.to.y = ky
                rm.resource_id = rid
                u.distribute_resources.moves.append(rm)
        case DiffUpdateHp(id=eid, delta=delta):
            u.update_hp.id = eid
            u.update_hp.delta = delta
        case DiffUpdatePlayers(players=players):
            u.update_players.players.a.titanium = players[0].titanium
            u.update_players.players.a.axionite = players[0].axionite
            u.update_players.players.a.resources_collected = players[
                0
            ].resources_collected
            u.update_players.players.a.titanium_collected = players[
                0
            ].titanium_collected
            u.update_players.players.a.axionite_collected = players[
                0
            ].axionite_collected
            u.update_players.players.b.titanium = players[1].titanium
            u.update_players.players.b.axionite = players[1].axionite
            u.update_players.players.b.resources_collected = players[
                1
            ].resources_collected
            u.update_players.players.b.titanium_collected = players[
                1
            ].titanium_collected
            u.update_players.players.b.axionite_collected = players[
                1
            ].axionite_collected
        case DiffSetActionCooldown(id=eid, value=val):
            u.set_action_cooldown.id = eid
            u.set_action_cooldown.value = val
        case DiffSetMoveCooldown(id=eid, value=val):
            u.set_move_cooldown.id = eid
            u.set_move_cooldown.value = val
        case DiffBotOutput(id=eid, stdout=stdout, exec_time_us=etus, tled=tled):
            u.bot_output.id = eid
            u.bot_output.stdout = stdout
            u.bot_output.exec_time_us = etus
            u.bot_output.tled = tled
        case DiffIndicatorLine(x1=ax, y1=ay, x2=bx, y2=by, r=r, g=g, b=b_):
            u.indicator_line.pos_a.x = ax
            u.indicator_line.pos_a.y = ay
            u.indicator_line.pos_b.x = bx
            u.indicator_line.pos_b.y = by
            u.indicator_line.r = r
            u.indicator_line.g = g
            u.indicator_line.b = b_
        case DiffIndicatorDot(x=px, y=py, r=r, g=g, b=b_):
            u.indicator_dot.pos.x = px
            u.indicator_dot.pos.y = py
            u.indicator_dot.r = r
            u.indicator_dot.g = g
            u.indicator_dot.b = b_
        case DiffFireTurret(from_x=fx, from_y=fy, to_x=tx, to_y=ty):
            u.fire_turret.CopyFrom(pb.FireTurret())
            getattr(u.fire_turret, "from").x = fx
            getattr(u.fire_turret, "from").y = fy
            u.fire_turret.to.x = tx
            u.fire_turret.to.y = ty
        case DiffBuilderBotAttack(id=eid):
            u.builder_attack.id = eid
    return u


def load_map(path: str) -> tuple[list[list[int]], list[tuple[int, int, int]]]:
    data = Path(path).read_bytes()

    map_msg = pb.Map()
    map_msg.ParseFromString(data)

    environment: list[list[int]] = [list(row.tiles) for row in map_msg.rows]

    cores: list[tuple[int, int, int]] = []
    for core in map_msg.cores:
        pos = core.position
        cores.append((pos.x, pos.y, core.team))

    has_a = any(t == 0 for _, _, t in cores)
    has_b = any(t == 1 for _, _, t in cores)
    if not has_a or not has_b:
        msg = "map must have a core for each team"
        raise OSError(msg)

    return environment, cores


def _patch_typing_compat() -> None:

    if not hasattr(typing, "override"):
        typing.override = lambda f: f

    import cambcpypy

    sys.modules["cambc"] = cambcpypy


_TYPE_STMT_RE = re.compile(r"^type\s+(\w+)\s*=", re.MULTILINE)


def _transpile_312_to_311(source: str) -> str:
    """Downgrade Python 3.12 syntax to 3.11-compatible equivalents."""
    return _TYPE_STMT_RE.sub(r"\1 =", source)


class _TranspilingLoader(Loader):
    """Wraps a file loader to transpile 3.12 syntax before execution."""

    def __init__(self, orig_loader: Loader | None, file_path: str) -> None:
        self._orig = orig_loader
        self._path = file_path

    def exec_module(self, module: types.ModuleType) -> None:
        source = Path(self._path).read_text(encoding="utf-8")
        source = _transpile_312_to_311(source)
        code = compile(source, self._path, "exec")
        exec(code, module.__dict__)  # noqa: S102


class _TranspilingFinder:
    """Meta path finder that intercepts imports from bot directories."""

    def __init__(self, bot_dir: str) -> None:
        self._bot_dir = bot_dir

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None,  # noqa: ARG002
        target: types.ModuleType | None = None,  # noqa: ARG002
    ) -> ModuleSpec | None:
        parts = fullname.split(".")
        candidate = Path(self._bot_dir)
        for part in parts:
            candidate = candidate / part

        pkg_init = candidate / "__init__.py"
        if pkg_init.is_file():
            spec = importlib.util.spec_from_file_location(
                fullname,
                str(pkg_init),
                submodule_search_locations=[str(candidate)],
            )
            if spec:
                spec.loader = _TranspilingLoader(spec.loader, str(pkg_init))
                return spec

        mod_file = candidate.with_suffix(".py")
        if mod_file.is_file():
            spec = importlib.util.spec_from_file_location(
                fullname,
                str(mod_file),
            )
            if spec:
                spec.loader = _TranspilingLoader(spec.loader, str(mod_file))
                return spec

        return None


def _load_player_class(bot_main: str) -> type:
    _patch_typing_compat()
    bot_dir = str(Path(bot_main).resolve().parent)

    saved_modules = sys.modules.copy()
    saved_path = sys.path[:]

    sys.path.insert(0, bot_dir)
    finder = _TranspilingFinder(bot_dir)
    sys.meta_path.insert(0, finder)
    try:
        spec = importlib.util.spec_from_file_location("bot_main", bot_main)
        assert spec is not None
        loader = _TranspilingLoader(spec.loader, bot_main)
        spec.loader = loader
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        return mod.Player
    finally:
        sys.meta_path.remove(finder)
        sys.path[:] = saved_path
        sys.modules.clear()
        sys.modules.update(saved_modules)


@dataclass(slots=True)
class GameResult:
    winner: int | None
    turns_played: int
    win_condition: str
    resign_message: str | None
    player_a_titanium: int
    player_a_axionite: int
    player_a_titanium_collected: int
    player_a_axionite_collected: int
    player_b_titanium: int
    player_b_axionite: int
    player_b_titanium_collected: int
    player_b_axionite_collected: int
    units_a: int
    units_b: int
    buildings_a: int
    buildings_b: int


class _Player(Protocol):
    def run(self, ct: object) -> None: ...


def run_game(
    player_a: str,
    player_b: str,
    engine_root: str,
    map_path: str,
    replay_path: str,
    seed: int = 1,
    turn_timeout_ms: int = 0,
    *,
    suppress_indicators: bool = False,
    quiet: bool = False,
) -> GameResult:
    py_dir = str(Path(engine_root) / "py")
    if py_dir not in sys.path:
        sys.path.insert(0, py_dir)

    environment, cores = load_map(map_path)
    game = Game(environment, cores, seed, suppress_indicators=suppress_indicators)

    random.seed(seed)

    player_classes: list[type] = []
    for bot_path in (player_a, player_b):
        cls = _load_player_class(bot_path)
        player_classes.append(cls)

    unit_runners: dict[int, _Player] = {}

    gc.disable()

    for i in range(GameConstants.MAX_TURNS):
        game.new_turn()

        for unit_id in list(game.unit_order):
            entity = game.entities.get(unit_id)
            if entity is None:
                continue
            team = entity.team
            team_idx = _TEAM_IDX[team]

            if unit_id not in unit_runners:
                try:
                    cls = player_classes[team_idx]
                    player_obj = cls()
                    unit_runners[unit_id] = player_obj
                except Exception:
                    traceback.print_exc()
                    if unit_id in game.entities:
                        game.destroy_entity(unit_id)
                    continue

            player_obj = unit_runners[unit_id]
            controller = Controller(game, unit_id)

            old_stdout = sys.stdout
            captured = StringIO()
            sys.stdout = captured

            t0 = time.perf_counter_ns()
            controller._turn_start = t0
            try:
                player_obj.run(controller)
            except SystemExit:
                pass
            except Exception:
                traceback.print_exc()
                if unit_id in game.entities:
                    game.destroy_entity(unit_id)
            finally:
                sys.stdout = old_stdout

            elapsed_us = (time.perf_counter_ns() - t0) // 1000
            stdout_text = captured.getvalue()
            tled = turn_timeout_ms > 0 and elapsed_us > turn_timeout_ms * 1000

            game._append_diff(
                DiffBotOutput(
                    id=unit_id,
                    stdout=stdout_text,
                    exec_time_us=elapsed_us,
                    tled=tled,
                ),
            )

        game.distribute_resources()
        game.apply_passive_income()
        game.update_cooldowns()

        players_snapshot = [copy.copy(p) for p in game.players]
        game._append_diff(DiffUpdatePlayers(players=players_snapshot))

        game.turn += 1

        dead = [uid for uid in list(unit_runners.keys()) if uid not in game.entities]
        for uid in dead:
            del unit_runners[uid]

        if not quiet and i % 100 == 0:
            print(f"Completed turn {i}")

        if game.winner_team()[0] is not None:
            break

    winner, win_condition = game.winner_team()
    if game.resign_message is not None:
        win_condition = "resigned"
    game.write_replay(replay_path, winner)

    units_a = 0
    units_b = 0
    buildings_a = 0
    buildings_b = 0
    for e in game.entities.values():
        is_unit_e = isinstance(e, (BuilderBot, Gunner, Sentinel, Breach, Launcher))
        if e.team is Team.A:
            if is_unit_e:
                units_a += 1
            else:
                buildings_a += 1
        elif is_unit_e:
            units_b += 1
        else:
            buildings_b += 1

    pa = game.players[0]
    pb_ = game.players[1]

    return GameResult(
        winner=_TEAM_IDX[winner] if winner is not None else None,
        turns_played=game.turn,
        win_condition=win_condition,
        resign_message=game.resign_message,
        player_a_titanium=pa.titanium,
        player_a_axionite=pa.axionite,
        player_a_titanium_collected=pa.titanium_collected,
        player_a_axionite_collected=pa.axionite_collected,
        player_b_titanium=pb_.titanium,
        player_b_axionite=pb_.axionite,
        player_b_titanium_collected=pb_.titanium_collected,
        player_b_axionite_collected=pb_.axionite_collected,
        units_a=units_a,
        units_b=units_b,
        buildings_a=buildings_a,
        buildings_b=buildings_b,
    )


_CARDINAL: set[Direction] = {
    Direction.NORTH,
    Direction.EAST,
    Direction.SOUTH,
    Direction.WEST,
}

_DIRECTIONAL: set[Direction] = {
    Direction.NORTH,
    Direction.NORTHEAST,
    Direction.EAST,
    Direction.SOUTHEAST,
    Direction.SOUTH,
    Direction.SOUTHWEST,
    Direction.WEST,
    Direction.NORTHWEST,
}

_ENTITY_TYPE_MAP: dict[type[Entity], EntityType] = {
    BuilderBot: EntityType.BUILDER_BOT,
    Core: EntityType.CORE,
    Conveyor: EntityType.CONVEYOR,
    Splitter: EntityType.SPLITTER,
    ArmouredConveyor: EntityType.ARMOURED_CONVEYOR,
    Bridge: EntityType.BRIDGE,
    Harvester: EntityType.HARVESTER,
    Foundry: EntityType.FOUNDRY,
    Road: EntityType.ROAD,
    Barrier: EntityType.BARRIER,
    Marker: EntityType.MARKER,
    Gunner: EntityType.GUNNER,
    Sentinel: EntityType.SENTINEL,
    Breach: EntityType.BREACH,
    Launcher: EntityType.LAUNCHER,
}


def _entity_type(e: Entity) -> EntityType:
    return _ENTITY_TYPE_MAP[type(e)]


class Controller:
    __slots__ = ("_game", "_placed_marker", "_turn_start", "_unit")

    def __init__(self, game: Game, unit_id: int) -> None:
        self._game: Game = game
        self._unit: int = unit_id
        self._placed_marker: bool = False
        self._turn_start: int = 0

    def _me(self) -> Entity:
        return self._game.entities[self._unit]

    def _ent(self, id: int) -> Entity:
        e = self._game.entities.get(id)
        if e is None:
            msg = "Unknown id"
            raise GameError(msg)
        return e

    def _in_bounds(self, x: int, y: int) -> bool:
        return self._game.in_bounds(x, y)

    def _team_idx(self) -> int:
        return 0 if self._me().team is Team.A else 1

    def _scaled_cost(self, base: tuple[int, int]) -> tuple[int, int]:
        team = self._me().team
        return self._game.scaled_cost(team, base)

    def _can_afford(self, cost: tuple[int, int]) -> bool:
        team = self._me().team
        return self._game.can_afford(team, cost)

    def get_team(self, id: int | None = None) -> Team:
        """Return the team of the entity with the given id, or this unit if omitted."""
        return self._ent(id if id is not None else self._unit).team

    def get_position(self, id: int | None = None) -> Position:
        """Return the position of the entity with the given id, or this unit if omitted."""
        e = self._ent(id if id is not None else self._unit)
        return Position(e.x, e.y)

    def get_id(self) -> int:
        """Return this unit's entity id."""
        return self._unit

    def get_action_cooldown(self) -> int:
        """Return this unit's current action cooldown. Actions require cooldown == 0."""
        me = self._me()
        if not isinstance(me, (BuilderBot, Core, Gunner, Sentinel, Breach, Launcher)):
            msg = "Unit is not a unit"
            raise GameError(msg)
        return me.action_cooldown

    def get_move_cooldown(self) -> int:
        """Return this unit's current move cooldown. Movement requires cooldown == 0."""
        me = self._me()
        if not isinstance(me, (BuilderBot, Core, Gunner, Sentinel, Breach, Launcher)):
            msg = "Unit is not a unit"
            raise GameError(msg)
        return me.move_cooldown

    def get_ammo_amount(self) -> int:
        """Return the amount of ammo this turret currently holds."""
        me = self._me()
        if not isinstance(me, (Gunner, Sentinel, Breach, Launcher)):
            msg = "Unit is not a turret"
            raise GameError(msg)
        return me.ammo_amount

    def get_ammo_type(self) -> ResourceType | None:
        """Return the resource type loaded as ammo, or None if empty."""
        me = self._me()
        if not isinstance(me, (Gunner, Sentinel, Breach, Launcher)):
            msg = "Unit is not a turret"
            raise GameError(msg)
        return me.ammo_type

    def get_vision_radius_sq(self, id: int | None = None) -> int:
        """Return the vision radius squared of the given unit, or this unit if omitted."""
        e = self._ent(id if id is not None else self._unit)
        if not isinstance(e, (BuilderBot, Core, Gunner, Sentinel, Breach, Launcher)):
            msg = "Unit is not a unit"
            raise GameError(msg)
        return vision_radius_sq(e)

    def get_hp(self, id: int | None = None) -> int:
        """Return the current HP of the entity with the given id, or this unit if omitted."""
        return self._ent(id if id is not None else self._unit).hp

    def get_max_hp(self, id: int | None = None) -> int:
        """Return the max HP of the entity with the given id, or this unit if omitted."""
        return self._ent(id if id is not None else self._unit).max_hp

    def get_entity_type(self, id: int | None = None) -> EntityType:
        """Return the EntityType of the entity with the given id, or this unit if omitted."""
        return _entity_type(self._ent(id if id is not None else self._unit))

    def get_direction(self, id: int | None = None) -> Direction:
        """Return the facing direction of a conveyor, splitter, armoured conveyor, or turret.
        Raises GameError if the entity has no direction.
        """
        e = self._ent(id if id is not None else self._unit)
        if isinstance(
            e,
            (Conveyor, Splitter, ArmouredConveyor, Gunner, Sentinel, Breach),
        ):
            return e.direction
        msg = "Entity has no direction"
        raise GameError(msg)

    def get_bridge_target(self, id: int) -> Position:
        """Return the output target position of a bridge. Raises GameError if not a bridge."""
        e = self._ent(id)
        if not isinstance(e, Bridge):
            msg = "Entity is not a bridge"
            raise GameError(msg)
        return Position(e.target_x, e.target_y)

    def get_stored_resource(self, id: int | None = None) -> ResourceType | None:
        """Return the resource stored in a conveyor, splitter, armoured conveyor, bridge, or foundry.
        Returns None if empty. Raises GameError if the entity has no storage.
        """
        e = self._ent(id if id is not None else self._unit)
        if isinstance(e, (Conveyor, Splitter, ArmouredConveyor, Bridge, Foundry)):
            return e.stored
        msg = "Entity has no stored resource"
        raise GameError(msg)

    def get_stored_resource_id(self, id: int | None = None) -> int | None:
        """Return the id of the resource stored in a conveyor, splitter, armoured conveyor, bridge, or foundry.
        Returns None if empty. Raises GameError if the entity has no storage.
        """
        e = self._ent(id if id is not None else self._unit)
        if isinstance(e, (Conveyor, Splitter, ArmouredConveyor, Bridge, Foundry)):
            return e.stored_id
        msg = "Entity has no stored resource"
        raise GameError(msg)

    def _assert_in_vision(self, pos: Position) -> None:
        if not self.is_in_vision(pos):
            msg = "Position is not in vision"
            raise GameError(msg)

    def get_tile_env(self, pos: Position) -> Environment:
        """Return the environment type (empty, wall, ore) of the tile at pos."""
        self._assert_in_vision(pos)
        return self._game.tiles[pos.y][pos.x].env

    def get_tile_building_id(self, pos: Position) -> int | None:
        """Return the id of the building on the tile at pos, or None if there is none."""
        self._assert_in_vision(pos)
        return self._game.tiles[pos.y][pos.x].building

    def get_tile_builder_bot_id(self, pos: Position) -> int | None:
        """Return the id of the builder bot on the tile at pos, or None if there is none."""
        self._assert_in_vision(pos)
        return self._game.tiles[pos.y][pos.x].bot

    def is_tile_empty(self, pos: Position) -> bool:
        """Return True if the tile has no building and is not a wall."""
        self._assert_in_vision(pos)
        return self._game.is_tile_empty(pos.x, pos.y)

    def is_tile_passable(self, pos: Position) -> bool:
        """Return True if a builder bot belonging to this team could stand on the tile."""
        self._assert_in_vision(pos)
        return self._game.is_tile_bot_passable(pos.x, pos.y, self._me().team)

    def is_in_vision(self, pos: Position) -> bool:
        """Return True if pos is within this unit's vision radius."""
        if not self._in_bounds(pos.x, pos.y):
            return False
        me = self._me()
        return pos.distance_squared(Position(me.x, me.y)) <= vision_radius_sq(me)

    def assert_entity_in_vision(self, _id: int) -> None:
        pass

    def get_nearby_tiles(self, dist_sq: int | None = None) -> list[Position]:
        """Return all in-bounds tile positions within dist_sq of this unit (defaults to vision radius)."""
        me = self._me()
        if not isinstance(me, (BuilderBot, Core, Gunner, Sentinel, Breach, Launcher)):
            msg = "Unit is not a unit"
            raise GameError(msg)
        vision = vision_radius_sq(me)
        if dist_sq is not None and dist_sq > vision:
            msg = "dist_sq exceeds vision radius"
            raise GameError(msg)
        rsq = dist_sq if dist_sq is not None else vision
        r = math.ceil(math.sqrt(rsq))
        mx, my = me.x, me.y
        w, h = self._game.width, self._game.height
        result: list[Position] = []
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dx * dx + dy * dy > rsq:
                    continue
                px, py = mx + dx, my + dy
                if 0 <= px < w and 0 <= py < h:
                    result.append(Position(px, py))
        return result

    def get_nearby_entities(self, dist_sq: int | None = None) -> list[int]:
        """Return ids of all entities on tiles within dist_sq (defaults to vision radius)."""
        tiles = self.get_nearby_tiles(dist_sq)
        seen: set[int] = set()
        result: list[int] = []
        for p in tiles:
            t = self._game.tiles[p.y][p.x]
            for eid in (t.building, t.bot):
                if eid is not None and eid not in seen:
                    seen.add(eid)
                    result.append(eid)
        return result

    def get_nearby_buildings(self, dist_sq: int | None = None) -> list[int]:
        """Return ids of all buildings within dist_sq (defaults to vision radius)."""
        ents = self._game.entities
        return [
            eid
            for eid in self.get_nearby_entities(dist_sq)
            if not isinstance(ents[eid], BuilderBot)
        ]

    def get_nearby_units(self, dist_sq: int | None = None) -> list[int]:
        """Return ids of all units within dist_sq (defaults to vision radius)."""
        ents = self._game.entities
        return [
            eid
            for eid in self.get_nearby_entities(dist_sq)
            if isinstance(
                ents[eid],
                (BuilderBot, Core, Gunner, Sentinel, Breach, Launcher),
            )
        ]

    def get_map_width(self) -> int:
        """Return the width of the map in tiles."""
        return self._game.width

    def get_map_height(self) -> int:
        """Return the height of the map in tiles."""
        return self._game.height

    def get_current_round(self) -> int:
        """Return the current round number (starts at 1)."""
        return self._game.turn

    def get_global_resources(self) -> tuple[int, int]:
        """Return (titanium, axionite) in this team's global resource pool."""
        ti = self._team_idx()
        p = self._game.players[ti]
        return (p.titanium, p.axionite)

    def get_scale_percent(self) -> float:
        """Return this team's current cost scale as a percentage (100.0 = base cost)."""
        ti = self._team_idx()
        return self._game.players[ti].scale_milli / 10.0

    def get_cpu_time_elapsed(self) -> int:
        """Return the CPU time elapsed this turn in microseconds."""
        return (time.perf_counter_ns() - self._turn_start) // 1000

    def get_unit_count(self) -> int:
        """Return the number of living units currently on this unit's team, including the core."""
        team = self._me().team
        return self._game.unit_count(team)

    def get_conveyor_cost(self) -> tuple[int, int]:
        """Return the current scaled cost (Ti, Ax) to build a conveyor."""
        return self._scaled_cost(GameConstants.CONVEYOR_BASE_COST)

    def get_splitter_cost(self) -> tuple[int, int]:
        """Return the current scaled cost (Ti, Ax) to build a splitter."""
        return self._scaled_cost(GameConstants.SPLITTER_BASE_COST)

    def get_bridge_cost(self) -> tuple[int, int]:
        """Return the current scaled cost (Ti, Ax) to build a bridge."""
        return self._scaled_cost(GameConstants.BRIDGE_BASE_COST)

    def get_armoured_conveyor_cost(self) -> tuple[int, int]:
        """Return the current scaled cost (Ti, Ax) to build an armoured conveyor."""
        return self._scaled_cost(GameConstants.ARMOURED_CONVEYOR_BASE_COST)

    def get_harvester_cost(self) -> tuple[int, int]:
        """Return the current scaled cost (Ti, Ax) to build a harvester."""
        return self._scaled_cost(GameConstants.HARVESTER_BASE_COST)

    def get_road_cost(self) -> tuple[int, int]:
        """Return the current scaled cost (Ti, Ax) to build a road."""
        return self._scaled_cost(GameConstants.ROAD_BASE_COST)

    def get_barrier_cost(self) -> tuple[int, int]:
        """Return the current scaled cost (Ti, Ax) to build a barrier."""
        return self._scaled_cost(GameConstants.BARRIER_BASE_COST)

    def get_gunner_cost(self) -> tuple[int, int]:
        """Return the current scaled cost (Ti, Ax) to build a gunner."""
        return self._scaled_cost(GameConstants.GUNNER_BASE_COST)

    def get_sentinel_cost(self) -> tuple[int, int]:
        """Return the current scaled cost (Ti, Ax) to build a sentinel."""
        return self._scaled_cost(GameConstants.SENTINEL_BASE_COST)

    def get_breach_cost(self) -> tuple[int, int]:
        """Return the current scaled cost (Ti, Ax) to build a breach."""
        return self._scaled_cost(GameConstants.BREACH_BASE_COST)

    def get_launcher_cost(self) -> tuple[int, int]:
        """Return the current scaled cost (Ti, Ax) to build a launcher."""
        return self._scaled_cost(GameConstants.LAUNCHER_BASE_COST)

    def get_foundry_cost(self) -> tuple[int, int]:
        """Return the current scaled cost (Ti, Ax) to build an axionite foundry."""
        return self._scaled_cost(GameConstants.FOUNDRY_BASE_COST)

    def get_builder_bot_cost(self) -> tuple[int, int]:
        """Return the current scaled cost (Ti, Ax) to spawn a builder bot."""
        return self._scaled_cost(GameConstants.BUILDER_BOT_BASE_COST)

    def _can_build_checks(self, px: int, py: int, base_cost: tuple[int, int]) -> bool:
        me = self._me()
        if not isinstance(me, BuilderBot):
            return False
        if me.action_cooldown > 0:
            return False
        dx = px - me.x
        dy = py - me.y
        if dx * dx + dy * dy > GameConstants.ACTION_RADIUS_SQ:
            return False
        if not self._in_bounds(px, py):
            return False
        tile = self._game.tiles[py][px]
        if tile.env is Environment.WALL:
            return False
        building_id = tile.building
        if building_id is not None:
            be = self._game.entities.get(building_id)
            if be is None or not isinstance(be, Marker):
                return False
        cost = self._scaled_cost(base_cost)
        return self._can_afford(cost)

    def can_move(self, direction: Direction) -> bool:
        """Return True if this builder bot can move in direction this turn."""
        me = self._me()
        if not isinstance(me, BuilderBot):
            return False
        if me.move_cooldown > 0:
            return False
        dx, dy = direction.delta()
        return self._game.is_tile_bot_passable(me.x + dx, me.y + dy, me.team)

    def move(self, direction: Direction) -> None:
        """Move this builder bot one step in direction. Raises GameError if the move is not legal."""
        if not self.can_move(direction):
            msg = "Cannot move"
            raise GameError(msg)
        me = self._me()
        dx, dy = direction.delta()
        new_x = me.x + dx
        new_y = me.y + dy
        self._game.move_builder_bot(self._unit, new_x, new_y)

    def can_build_conveyor(self, position: Position, direction: Direction) -> bool:
        """Return True if a conveyor facing direction can be built at position."""
        if direction not in _CARDINAL:
            return False
        return self._can_build_checks(
            position.x,
            position.y,
            GameConstants.CONVEYOR_BASE_COST,
        )

    def can_build_splitter(self, position: Position, direction: Direction) -> bool:
        """Return True if a splitter facing direction can be built at position."""
        if direction not in _CARDINAL:
            return False
        return self._can_build_checks(
            position.x,
            position.y,
            GameConstants.SPLITTER_BASE_COST,
        )

    def can_build_bridge(self, position: Position, target: Position) -> bool:
        """Return True if a bridge outputting to target can be built at position."""
        if not self._can_build_checks(
            position.x,
            position.y,
            GameConstants.BRIDGE_BASE_COST,
        ):
            return False
        if not self._in_bounds(target.x, target.y):
            return False
        dx = position.x - target.x
        dy = position.y - target.y
        dsq = dx * dx + dy * dy
        return 0 < dsq <= GameConstants.BRIDGE_TARGET_RADIUS_SQ

    def can_build_armoured_conveyor(
        self,
        position: Position,
        direction: Direction,
    ) -> bool:
        """Return True if an armoured conveyor facing direction can be built at position."""
        if direction not in _CARDINAL:
            return False
        return self._can_build_checks(
            position.x,
            position.y,
            GameConstants.ARMOURED_CONVEYOR_BASE_COST,
        )

    def can_build_harvester(self, position: Position) -> bool:
        """Return True if a harvester can be built at position (must be an ore tile)."""
        if not self._can_build_checks(
            position.x,
            position.y,
            GameConstants.HARVESTER_BASE_COST,
        ):
            return False
        tile = self._game.tiles[position.y][position.x]
        if tile.bot is not None:
            return False
        env = tile.env
        return env in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE)

    def can_build_road(self, position: Position) -> bool:
        """Return True if a road can be built at position."""
        return self._can_build_checks(
            position.x,
            position.y,
            GameConstants.ROAD_BASE_COST,
        )

    def can_build_barrier(self, position: Position) -> bool:
        """Return True if a barrier can be built at position."""
        if not self._can_build_checks(
            position.x,
            position.y,
            GameConstants.BARRIER_BASE_COST,
        ):
            return False
        tile = self._game.tiles[position.y][position.x]
        return tile.bot is None

    def can_build_gunner(self, position: Position, direction: Direction) -> bool:
        """Return True if a gunner facing direction can be built at position."""
        if direction not in _DIRECTIONAL:
            return False
        if not self._can_build_checks(
            position.x,
            position.y,
            GameConstants.GUNNER_BASE_COST,
        ):
            return False
        tile = self._game.tiles[position.y][position.x]
        if tile.bot is not None:
            return False
        return self._game.unit_count(self._me().team) < 50

    def can_build_sentinel(self, position: Position, direction: Direction) -> bool:
        """Return True if a sentinel facing direction can be built at position."""
        if direction not in _DIRECTIONAL:
            return False
        if not self._can_build_checks(
            position.x,
            position.y,
            GameConstants.SENTINEL_BASE_COST,
        ):
            return False
        tile = self._game.tiles[position.y][position.x]
        if tile.bot is not None:
            return False
        return self._game.unit_count(self._me().team) < 50

    def can_build_breach(self, position: Position, direction: Direction) -> bool:
        """Return True if a breach facing direction can be built at position."""
        if direction not in _DIRECTIONAL:
            return False
        if not self._can_build_checks(
            position.x,
            position.y,
            GameConstants.BREACH_BASE_COST,
        ):
            return False
        tile = self._game.tiles[position.y][position.x]
        if tile.bot is not None:
            return False
        return self._game.unit_count(self._me().team) < 50

    def can_build_launcher(self, position: Position) -> bool:
        """Return True if a launcher can be built at position."""
        if not self._can_build_checks(
            position.x,
            position.y,
            GameConstants.LAUNCHER_BASE_COST,
        ):
            return False
        tile = self._game.tiles[position.y][position.x]
        if tile.bot is not None:
            return False
        return self._game.unit_count(self._me().team) < 50

    def can_build_foundry(self, position: Position) -> bool:
        """Return True if an axionite foundry can be built at position."""
        if not self._can_build_checks(
            position.x,
            position.y,
            GameConstants.FOUNDRY_BASE_COST,
        ):
            return False
        tile = self._game.tiles[position.y][position.x]
        return tile.bot is None

    def build_conveyor(self, position: Position, direction: Direction) -> int:
        """Build a conveyor facing direction at position. Raises GameError if not legal."""
        if not self.can_build_conveyor(position, direction):
            msg = "Cannot build conveyor"
            raise GameError(msg)
        return self._game.build_conveyor(self._unit, position.x, position.y, direction)

    def build_splitter(self, position: Position, direction: Direction) -> int:
        """Build a splitter facing direction at position. Raises GameError if not legal."""
        if not self.can_build_splitter(position, direction):
            msg = "Cannot build splitter"
            raise GameError(msg)
        return self._game.build_splitter(self._unit, position.x, position.y, direction)

    def build_bridge(self, position: Position, target: Position) -> int:
        """Build a bridge at position outputting to target. Raises GameError if not legal."""
        if not self.can_build_bridge(position, target):
            msg = "Cannot build bridge"
            raise GameError(msg)
        return self._game.build_bridge(
            self._unit,
            position.x,
            position.y,
            target.x,
            target.y,
        )

    def build_armoured_conveyor(self, position: Position, direction: Direction) -> int:
        """Build an armoured conveyor facing direction at position. Raises GameError if not legal."""
        if not self.can_build_armoured_conveyor(position, direction):
            msg = "Cannot build armoured conveyor"
            raise GameError(msg)
        return self._game.build_armoured_conveyor(
            self._unit,
            position.x,
            position.y,
            direction,
        )

    def build_harvester(self, position: Position) -> int:
        """Build a harvester at position. Raises GameError if not legal."""
        if not self.can_build_harvester(position):
            msg = "Cannot build harvester"
            raise GameError(msg)
        return self._game.build_harvester(self._unit, position.x, position.y)

    def build_road(self, position: Position) -> int:
        """Build a road at position. Raises GameError if not legal."""
        if not self.can_build_road(position):
            msg = "Cannot build road"
            raise GameError(msg)
        return self._game.build_road(self._unit, position.x, position.y)

    def build_barrier(self, position: Position) -> int:
        """Build a barrier at position. Raises GameError if not legal."""
        if not self.can_build_barrier(position):
            msg = "Cannot build barrier"
            raise GameError(msg)
        return self._game.build_barrier(self._unit, position.x, position.y)

    def build_gunner(self, position: Position, direction: Direction) -> int:
        """Build a gunner facing direction at position. Raises GameError if not legal."""
        if not self.can_build_gunner(position, direction):
            msg = "Cannot build gunner"
            raise GameError(msg)
        return self._game.build_gunner(self._unit, position.x, position.y, direction)

    def build_sentinel(self, position: Position, direction: Direction) -> int:
        """Build a sentinel facing direction at position. Raises GameError if not legal."""
        if not self.can_build_sentinel(position, direction):
            msg = "Cannot build sentinel"
            raise GameError(msg)
        return self._game.build_sentinel(self._unit, position.x, position.y, direction)

    def build_breach(self, position: Position, direction: Direction) -> int:
        """Build a breach facing direction at position. Raises GameError if not legal."""
        if not self.can_build_breach(position, direction):
            msg = "Cannot build breach"
            raise GameError(msg)
        return self._game.build_breach(self._unit, position.x, position.y, direction)

    def build_launcher(self, position: Position) -> int:
        """Build a launcher at position. Raises GameError if not legal."""
        if not self.can_build_launcher(position):
            msg = "Cannot build launcher"
            raise GameError(msg)
        return self._game.build_launcher(self._unit, position.x, position.y)

    def build_foundry(self, position: Position) -> int:
        """Build an axionite foundry at position. Raises GameError if not legal."""
        if not self.can_build_foundry(position):
            msg = "Cannot build foundry"
            raise GameError(msg)
        return self._game.build_foundry(self._unit, position.x, position.y)

    def can_heal(self, position: Position) -> bool:
        """Return True if this builder bot can heal the tile at position this turn."""
        me = self._me()
        if not isinstance(me, BuilderBot):
            return False
        if me.action_cooldown > 0:
            return False
        dx = position.x - me.x
        dy = position.y - me.y
        if dx * dx + dy * dy > GameConstants.ACTION_RADIUS_SQ:
            return False
        if not self._in_bounds(position.x, position.y):
            return False
        if not self._can_afford((1, 0)):
            return False
        my_team = me.team
        tile = self._game.tiles[position.y][position.x]
        for eid in (tile.building, tile.bot):
            if eid is not None:
                e = self._game.entities.get(eid)
                if e is not None and e.team is my_team and e.hp < e.max_hp:
                    return True
        return False

    def heal(self, position: Position) -> None:
        """Heal all friendly entities on a tile within this builder bot's action radius by 4 HP."""
        if not self.can_heal(position):
            msg = "Cannot heal"
            raise GameError(msg)
        me = self._me()
        assert isinstance(me, BuilderBot)
        team = me.team
        self._game.spend(team, (1, 0))

        me.action_cooldown += 1
        self._game._append_diff(
            DiffSetActionCooldown(id=self._unit, value=me.action_cooldown),
        )
        self._game.heal_tile(position.x, position.y, team)

    def can_destroy(self, building_pos: Position) -> bool:
        """Return True if this builder bot can destroy the allied building at building_pos."""
        me = self._me()
        if not isinstance(me, (BuilderBot, Core, Gunner, Sentinel, Breach, Launcher)):
            return False
        if not self._in_bounds(building_pos.x, building_pos.y):
            return False
        tile = self._game.tiles[building_pos.y][building_pos.x]
        building_id = tile.building
        if building_id is None:
            return False
        be = self._game.entities.get(building_id)
        if be is None:
            return False
        if isinstance(be, Core):
            return False
        if be.team is not me.team:
            return False
        if isinstance(be, Marker):
            arsq = action_radius_sq(me)
            dx = building_pos.x - me.x
            dy = building_pos.y - me.y
            return dx * dx + dy * dy <= arsq
        if not isinstance(me, BuilderBot):
            return False
        dx = building_pos.x - me.x
        dy = building_pos.y - me.y
        return dx * dx + dy * dy <= GameConstants.ACTION_RADIUS_SQ

    def destroy(self, building_pos: Position) -> None:
        """Destroy the allied building at building_pos. Raises GameError if not legal."""
        if not self.can_destroy(building_pos):
            msg = "Cannot destroy"
            raise GameError(msg)
        tile = self._game.tiles[building_pos.y][building_pos.x]
        building_id = tile.building
        if building_id is not None:
            self._game.destroy_entity(building_id)

    def self_destruct(self) -> None:
        """Destroy this unit."""
        me = self._me()
        if isinstance(me, BuilderBot):
            x, y = me.x, me.y
            self._game.destroy_entity(self._unit)
            if GameConstants.BUILDER_BOT_SELF_DESTRUCT_DAMAGE > 0:
                self._game.damage_tile(
                    x,
                    y,
                    GameConstants.BUILDER_BOT_SELF_DESTRUCT_DAMAGE,
                )
        else:
            self._game.destroy_entity(self._unit)
        raise SystemExit

    def resign(self, message: str | None = None) -> None:
        """Forfeit the game immediately. Destroys this team's core."""
        self._game.resign_message = message
        team = self._me().team
        for eid in list(self._game.entities.keys()):
            e = self._game.entities.get(eid)
            if e is not None and isinstance(e, Core) and e.team is team:
                self._game.destroy_entity(eid)
        raise SystemExit

    def can_place_marker(self, position: Position) -> bool:
        """Return True if this unit can place a marker at position this turn."""
        if self._placed_marker:
            return False
        me = self._me()
        if not isinstance(me, (BuilderBot, Core, Gunner, Sentinel, Breach, Launcher)):
            return False
        arsq = action_radius_sq(me)
        if not self._in_bounds(position.x, position.y):
            return False
        dx = position.x - me.x
        dy = position.y - me.y
        if dx * dx + dy * dy > arsq:
            return False
        tile = self._game.tiles[position.y][position.x]
        if tile.env is Environment.WALL:
            return False
        building_id = tile.building
        if building_id is None:
            return True
        be = self._game.entities.get(building_id)
        if be is None:
            return True
        return isinstance(be, Marker) and be.team is me.team

    def place_marker(self, position: Position, value: int) -> None:
        """Place a marker with the given u32 value at position. Raises GameError if not legal."""
        if not self.can_place_marker(position):
            msg = "Cannot place marker"
            raise GameError(msg)
        team = self._me().team
        self._game.place_marker(team, position.x, position.y, value)
        self._placed_marker = True

    def get_marker_value(self, id: int) -> int:
        """Return the u32 value stored in the friendly marker with the given id."""
        e = self._ent(id)
        if not isinstance(e, Marker):
            msg = "Entity is not a marker"
            raise GameError(msg)
        if e.team is not self._me().team:
            msg = "Marker belongs to enemy team"
            raise GameError(msg)
        return e.value

    def can_fire(self, target: Position) -> bool:
        """Return True if this builder bot or turret can fire at target this turn."""
        me = self._me()
        if isinstance(me, (Gunner, Sentinel, Breach)):
            if me.action_cooldown > 0:
                return False
            if me.ammo_amount <= 0:
                return False
            if isinstance(me, Gunner):
                gt = self._game.gunner_target(self._unit)
                return gt is not None and gt[0] == target.x and gt[1] == target.y
            if isinstance(me, Sentinel):
                return self._game.sentinel_target_valid(self._unit, target.x, target.y)
            if isinstance(me, Breach):
                return self._game.breach_target_valid(self._unit, target.x, target.y)
        elif isinstance(me, Launcher):
            return False
        elif isinstance(me, BuilderBot):
            if me.action_cooldown > 0:
                return False
            if target.x != me.x or target.y != me.y:
                return False
            if not self._can_afford((2, 0)):
                return False
            tile = self._game.tiles[me.y][me.x]
            building_id = tile.building
            if building_id is None:
                return False
            be = self._game.entities.get(building_id)
            if be is None:
                return False
            if isinstance(be, ArmouredConveyor):
                return False
            return be.team is not me.team
        else:
            return False
        return False

    def fire(self, target: Position) -> None:
        """Fire this builder bot or turret at target. Raises GameError if not legal."""
        me = self._me()
        if isinstance(me, Launcher):
            msg = "Use launch() for launchers, not fire()"
            raise GameError(msg)
        if not self.can_fire(target):
            msg = "Cannot fire"
            raise GameError(msg)
        if isinstance(me, Gunner):
            axionite = me.ammo_type is ResourceType.REFINED_AXIONITE
            self._game.fire_gunner(self._unit, axionite=axionite)
        elif isinstance(me, Sentinel):
            axionite = me.ammo_type is ResourceType.REFINED_AXIONITE
            self._game.fire_sentinel(self._unit, target.x, target.y, axionite=axionite)
        elif isinstance(me, Breach):
            self._game.fire_breach(self._unit, target.x, target.y)
        elif isinstance(me, BuilderBot):
            tile = self._game.tiles[me.y][me.x]
            building_id = tile.building
            if building_id is not None:
                self._game.builder_bot_attack(self._unit, building_id)

    def get_gunner_target(self) -> Position | None:
        """Return the position of the closest targetable tile in the gunner's facing direction."""
        me = self._me()
        if not isinstance(me, Gunner):
            msg = "Unit is not a gunner"
            raise GameError(msg)
        result = self._game.gunner_target(self._unit)
        if result is None:
            return None
        return Position(result[0], result[1])

    def can_launch(self, bot_pos: Position, target: Position) -> bool:
        """Return True if this launcher can pick up the builder bot at bot_pos and throw it to target."""
        me = self._me()
        if not isinstance(me, Launcher):
            return False
        if me.action_cooldown > 0:
            return False
        if not self._in_bounds(bot_pos.x, bot_pos.y):
            return False
        dx = bot_pos.x - me.x
        dy = bot_pos.y - me.y
        if dx * dx + dy * dy > GameConstants.ACTION_RADIUS_SQ:
            return False
        tile = self._game.tiles[bot_pos.y][bot_pos.x]
        bot_id = tile.bot
        if bot_id is None:
            return False
        if not self._game.launcher_target_valid(self._unit, target.x, target.y):
            return False
        bot_ent = self._game.entities.get(bot_id)
        if bot_ent is None:
            return False
        return self._game.is_tile_bot_passable(target.x, target.y, bot_ent.team)

    def launch(self, bot_pos: Position, target: Position) -> None:
        """Pick up the builder bot at bot_pos and throw it to target. Raises GameError if not legal."""
        me = self._me()
        if not isinstance(me, Launcher):
            msg = "Unit is not a launcher"
            raise GameError(msg)
        if not self.can_launch(bot_pos, target):
            msg = "Cannot launch"
            raise GameError(msg)
        self._game.launch_bot(self._unit, bot_pos.x, bot_pos.y, target.x, target.y)

    def get_attackable_tiles(self) -> list[Position]:
        """Return all in-bounds tiles in this turret's raw attack pattern."""
        me = self._me()
        if isinstance(me, Launcher):
            msg = "Launchers have no attack pattern"
            raise GameError(msg)
        if isinstance(me, Gunner):
            result = self._game.gunner_attackable_tiles(me.x, me.y, me.direction)
        elif isinstance(me, Sentinel):
            result = self._game.sentinel_attackable_tiles(me.x, me.y, me.direction)
        elif isinstance(me, Breach):
            result = self._game.breach_attackable_tiles(me.x, me.y, me.direction)
        else:
            msg = "Unit is not a turret"
            raise GameError(msg)
        return [Position(r[0], r[1]) for r in result]

    def get_attackable_tiles_from(
        self,
        position: Position,
        direction: Direction,
        turret_type: EntityType,
    ) -> list[Position]:
        """Return all in-bounds tiles in a hypothetical turret's raw attack pattern."""
        if turret_type is EntityType.GUNNER:
            result = self._game.gunner_attackable_tiles(
                position.x,
                position.y,
                direction,
            )
        elif turret_type is EntityType.SENTINEL:
            result = self._game.sentinel_attackable_tiles(
                position.x,
                position.y,
                direction,
            )
        elif turret_type is EntityType.BREACH:
            result = self._game.breach_attackable_tiles(
                position.x,
                position.y,
                direction,
            )
        else:
            msg = "Invalid turret type"
            raise GameError(msg)
        return [Position(r[0], r[1]) for r in result]

    def can_fire_from(
        self,
        position: Position,
        direction: Direction,
        turret_type: EntityType,
        target: Position,
    ) -> bool:
        """Return True if a hypothetical turret at position facing direction could fire at target."""
        tiles = self.get_attackable_tiles_from(position, direction, turret_type)
        return target in tiles

    def can_spawn(self, position: Position) -> bool:
        """Return True if the core can spawn a builder bot at position this turn."""
        me = self._me()
        if not isinstance(me, Core):
            return False
        if me.action_cooldown > 0:
            return False
        dx = position.x - me.x
        dy = position.y - me.y
        if dx * dx + dy * dy > GameConstants.CORE_SPAWNING_RADIUS_SQ:
            return False
        if not self._game.is_tile_bot_passable(position.x, position.y, me.team):
            return False
        if self._game.unit_count(me.team) >= 50:
            return False
        cost = self._scaled_cost(GameConstants.BUILDER_BOT_BASE_COST)
        return self._can_afford(cost)

    def spawn_builder(self, position: Position) -> int:
        """Spawn a builder bot on one of the 9 core tiles at position. Raises GameError if not legal."""
        if not self.can_spawn(position):
            msg = "Cannot spawn"
            raise GameError(msg)
        return self._game.spawn_builder(self._unit, position.x, position.y)

    def can_rotate(self, direction: Direction) -> bool:
        """Return True if this gunner can rotate to a different compass direction this turn."""
        me = self._me()
        if not isinstance(me, Gunner):
            return False
        if me.action_cooldown > 0:
            return False
        if direction not in _DIRECTIONAL:
            return False
        if me.direction is direction:
            return False
        return self._can_afford((10, 0))

    def rotate(self, direction: Direction) -> None:
        """Rotate this gunner to a different compass direction. Raises GameError if not legal."""
        if not self.can_rotate(direction):
            msg = "Cannot rotate"
            raise GameError(msg)
        self._game.rotate_gunner(self._unit, direction)

    def convert(self, amount: int) -> None:
        """Convert amount refined axionite into 4x titanium. Only valid on cores."""
        me = self._me()
        if not isinstance(me, Core):
            msg = "Unit is not a core"
            raise GameError(msg)
        if amount <= 0:
            msg = "Amount must be positive"
            raise GameError(msg)
        ti = self._team_idx()
        if self._game.players[ti].axionite < amount:
            msg = "Not enough axionite"
            raise GameError(msg)
        self._game.convert(me.team, amount)

    def draw_indicator_line(
        self,
        pos_a: Position,
        pos_b: Position,
        r: int,
        g: int,
        b: int,
    ) -> None:
        """Draw a debug line from pos_a to pos_b with RGB colour. Saved to the replay."""
        self._game._append_diff(
            DiffIndicatorLine(
                x1=pos_a.x,
                y1=pos_a.y,
                x2=pos_b.x,
                y2=pos_b.y,
                r=r,
                g=g,
                b=b,
            ),
        )

    def draw_indicator_dot(self, pos: Position, r: int, g: int, b: int) -> None:
        """Draw a debug dot at pos with RGB colour. Saved to the replay."""
        self._game._append_diff(DiffIndicatorDot(x=pos.x, y=pos.y, r=r, g=g, b=b))

    def can_build(
        self,
        entity_type: EntityType,
        position: Position,
        extra: Direction | Position | None = None,
    ) -> bool:
        """Return True if entity_type can be built at position."""
        if entity_type is EntityType.CONVEYOR:
            return self.can_build_conveyor(position, extra)
        if entity_type is EntityType.SPLITTER:
            return self.can_build_splitter(position, extra)
        if entity_type is EntityType.ARMOURED_CONVEYOR:
            return self.can_build_armoured_conveyor(position, extra)
        if entity_type is EntityType.BRIDGE:
            return self.can_build_bridge(position, extra)
        if entity_type is EntityType.GUNNER:
            return self.can_build_gunner(position, extra)
        if entity_type is EntityType.SENTINEL:
            return self.can_build_sentinel(position, extra)
        if entity_type is EntityType.BREACH:
            return self.can_build_breach(position, extra)
        if entity_type is EntityType.HARVESTER:
            return self.can_build_harvester(position)
        if entity_type is EntityType.ROAD:
            return self.can_build_road(position)
        if entity_type is EntityType.BARRIER:
            return self.can_build_barrier(position)
        if entity_type is EntityType.LAUNCHER:
            return self.can_build_launcher(position)
        if entity_type is EntityType.FOUNDRY:
            return self.can_build_foundry(position)
        msg = f"Unknown entity type: {entity_type}"
        raise GameError(msg)

    def build(
        self,
        entity_type: EntityType,
        position: Position,
        extra: Direction | Position | None = None,
    ) -> int:
        """Build entity_type at position. Raises GameError if not legal."""
        if entity_type is EntityType.CONVEYOR:
            return self.build_conveyor(position, extra)
        if entity_type is EntityType.SPLITTER:
            return self.build_splitter(position, extra)
        if entity_type is EntityType.ARMOURED_CONVEYOR:
            return self.build_armoured_conveyor(position, extra)
        if entity_type is EntityType.BRIDGE:
            return self.build_bridge(position, extra)
        if entity_type is EntityType.GUNNER:
            return self.build_gunner(position, extra)
        if entity_type is EntityType.SENTINEL:
            return self.build_sentinel(position, extra)
        if entity_type is EntityType.BREACH:
            return self.build_breach(position, extra)
        if entity_type is EntityType.HARVESTER:
            return self.build_harvester(position)
        if entity_type is EntityType.ROAD:
            return self.build_road(position)
        if entity_type is EntityType.BARRIER:
            return self.build_barrier(position)
        if entity_type is EntityType.LAUNCHER:
            return self.build_launcher(position)
        if entity_type is EntityType.FOUNDRY:
            return self.build_foundry(position)
        msg = f"Unknown entity type: {entity_type}"
        raise GameError(msg)
