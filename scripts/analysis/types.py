from __future__ import annotations

from dataclasses import dataclass, field

from .constants import Pos


@dataclass
class MapMeta:
    width: int
    height: int
    core_pos: dict[int, Pos]
    ore_tiles: list[tuple[int, int, str]]
    passable_count: int


@dataclass
class EntityState:
    id: int
    team: int
    kind: str
    pos: Pos
    hp: int
    max_hp: int
    direction: int = 0
    bridge_target: Pos | None = None


@dataclass
class GameState:
    turn: int
    width: int
    height: int
    tiles: list[list[int]]
    core_pos: dict[int, Pos]
    entities: dict[int, EntityState]
    building_at: dict[Pos, int]
    resources: dict[int, ResourceSnapshot]
    flow_events: list[tuple[Pos, Pos]]


@dataclass
class ResourceSnapshot:
    turn: int
    titanium: int
    axionite: int
    titanium_collected: int
    axionite_collected: int


@dataclass
class DamageEvent:
    turn: int
    damage: int
    victim_type: str


@dataclass
class ScanData:
    total_turns: int
    winner: str

    resource_history: dict[int, list[ResourceSnapshot]] = field(default_factory=dict)
    entities_placed: dict[int, dict[str, int]] = field(default_factory=dict)
    entities_removed: dict[int, dict[str, int]] = field(default_factory=dict)
    entities_alive: dict[int, dict[str, int]] = field(default_factory=dict)
    first_built: dict[int, dict[str, int]] = field(default_factory=dict)
    total_moves: dict[int, int] = field(default_factory=dict)
    total_damage: dict[int, int] = field(default_factory=dict)
    entity_kills: dict[int, int] = field(default_factory=dict)
    builder_kills: dict[int, int] = field(default_factory=dict)
    self_destructs: dict[int, int] = field(default_factory=dict)
    self_destruct_turns: dict[int, list[int]] = field(default_factory=dict)
    tle_count: dict[int, int] = field(default_factory=dict)
    exec_time_total: dict[int, int] = field(default_factory=dict)
    exec_time_samples: dict[int, int] = field(default_factory=dict)
    max_exec_time: dict[int, int] = field(default_factory=dict)
    fire_count: dict[int, dict[str, int]] = field(default_factory=dict)

    conveyor_moves_per_turn: list[int] = field(default_factory=list)
    conveyor_flow_count: dict[tuple[Pos, Pos], int] = field(default_factory=dict)
    first_resource_turn: dict[int, int | None] = field(default_factory=dict)
    income_rate: dict[int, list[tuple[int, float]]] = field(default_factory=dict)
    top_flow_tiles: list[tuple[Pos, int]] = field(default_factory=list)

    damage_events: dict[int, list[DamageEvent]] = field(default_factory=dict)
    damage_by_victim: dict[int, dict[str, int]] = field(default_factory=dict)
    buildings_destroyed: dict[int, dict[str, int]] = field(default_factory=dict)
    builder_losses: dict[int, int] = field(default_factory=dict)
    turrets_built: dict[int, dict[str, int]] = field(default_factory=dict)
    turret_shots: dict[int, dict[str, int]] = field(default_factory=dict)
    raid_arrivals: dict[int, list[int]] = field(default_factory=dict)
    core_hp_timeline: dict[int, list[tuple[int, int]]] = field(default_factory=dict)

    first_conveyor_killed_turn: dict[int, int | None] = field(default_factory=dict)
    first_chain_break_turn: dict[int, int | None] = field(default_factory=dict)
    chain_repairs: dict[int, int] = field(default_factory=dict)

    core_deliveries_per_turn: dict[int, dict[int, int]] = field(default_factory=dict)
    harvester_output_per_turn: dict[int, dict[int, int]] = field(default_factory=dict)
    first_delivery_turn: dict[int, int | None] = field(default_factory=dict)

    builder_idle_turns: dict[int, int] = field(default_factory=dict)
    builder_presence_turns: dict[int, int] = field(default_factory=dict)
    builder_born: dict[int, int] = field(default_factory=dict)
    builder_death: dict[int, int] = field(default_factory=dict)
    builder_team: dict[int, int] = field(default_factory=dict)
    builder_actions: dict[int, list[tuple[int, str]]] = field(default_factory=dict)
    builder_pos_history: dict[int, list[tuple[int, Pos]]] = field(default_factory=dict)

    harvester_count: dict[int, int] = field(default_factory=dict)
    harvesters_connected: dict[int, int] = field(default_factory=dict)


@dataclass
class Context:
    map_meta: MapMeta
    replay_path: str
    snapshots: list[GameState] | None = None
    scan: ScanData | None = None
