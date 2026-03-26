from __future__ import annotations

from builder import run_builder
from cambc import Controller, Direction, EntityType, Environment, Position
from core import run_core
from gunner import run_gunner
from launcher import run_launcher
from pathfinding import AgentState
from utils import (
    PHASE_SCOUTING,
    SYM_TYPES,
    BuilderState,
    Symmetry,
)


class Player:
    def __init__(self) -> None:
        self.core_pos: Position | None = None
        self.enemy_core: Position | None = None
        self.sym_resolved: Symmetry | None = None
        self.sym_candidates: dict[Symmetry, Position] | None = None
        self.sym_eliminated: set[Symmetry] = set()
        self.known_env: dict[Position, Environment] = {}

        self.spawned = 0
        self.base_builders_spawned: int = 0
        self.core_phase = PHASE_SCOUTING
        self.no_report_rounds = 0
        self.launch_wait: int = 0
        self.launch_bot_id: int | None = None
        self.next_spawn_economy: bool = False
        self.known_splitters: dict | None = None
        self.splitter_resource_counts: dict = {}
        self.splitter_respawn_queue: list = []
        self.busiest_spawned_dirs: dict = {}
        self.last_hp: int | None = None
        self.damage_spawns_remaining: int = 0
        self.max_hp_turns: int = 0

        self.spawned_economy: int = 0
        self.spawned_advance: int = 0

        self.economy_wandering: int = 0
        self.economy_wait_turns: int = 0
        self.base_round: int = 0
        self.state: BuilderState | None = None
        self.target: Position | None = None
        self.base_phase: int = 0
        self.base_wait: int = 0
        self.seen_launcher: bool = False
        self.advance_ore: set[Position] = set()
        self.advance_targeting_ore: bool = False
        self.state_seen_enemy: bool = False
        self.suicide_countdown: int = 0
        self.built_launcher: bool = False
        self.idle_empty_turns: int = 0
        self.tile_resource_seen: dict = {}
        self.heal_no_harvester_turns: int = 0
        self.can_patch: bool = False
        self.state_turns: int = 0
        self.prev_state: BuilderState | None = None

        self.known_ore: set[Position] = set()
        self.claimed_ore: set[Position] = set()
        self.last_dir: Direction | None = None
        self.bridge_target: Position | None = None

        self.pf_agent: AgentState = AgentState(Position(0, 0), Position(0, 0))
        self.pf_stuck: int = 0
        self.pf_prev_pos: Position | None = None
        self.pf_prev_pos2: Position | None = None
        self.pf_prev_pos3: Position | None = None

    def try_resolve(self, w: int, h: int, tag: str) -> bool:
        if self.sym_resolved:
            return True
        if self.sym_candidates is None:
            return False
        remaining = [s for s in SYM_TYPES if s not in self.sym_eliminated]
        resolved_sym = None
        resolved_pos = None
        if len(remaining) == 1:
            resolved_sym = remaining[0]
            resolved_pos = self.sym_candidates[remaining[0]]
        elif len(remaining) > 1:
            positions = {self.sym_candidates[s] for s in remaining}
            if len(positions) == 1:
                resolved_sym = remaining[0]
                resolved_pos = positions.pop()

        if resolved_sym and resolved_pos:
            self.sym_resolved = resolved_sym
            self.enemy_core = resolved_pos
            print(
                f"{tag}: resolved [{resolved_sym.value}] -> "
                f"({resolved_pos.x},{resolved_pos.y})",
            )
            return True
        return False

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            run_core(self, ct)
        elif etype == EntityType.BUILDER_BOT:
            run_builder(self, ct)
        elif etype == EntityType.LAUNCHER:
            run_launcher(self, ct)
        elif etype == EntityType.GUNNER:
            run_gunner(self, ct)
