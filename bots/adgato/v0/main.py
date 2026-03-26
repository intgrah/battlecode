"""v5 bot - barrier rush.

Phase 1 (Scout): Core spawns 3 scouts, each assigned to a different
candidate enemy core position (determined by entity_id % 3). Core
spawns each scout on the core tile closest to its candidate so they
leave in different directions. Scouts navigate using Bug2 pathfinding
(M-line toward target with left-hand wall-following when blocked),
preferring existing walkable tiles (enemy or friendly) over building
roads. Symmetry elimination runs every turn. The scout whose candidate
is confirmed heads to the enemy core and reports back; scouts whose
candidates are eliminated go idle.

Phases 2-3 (Assault, Economy): not yet implemented.
"""

from adgato_builder import run_builder
from adgato_core import run_core
from cambc import Controller, Direction, EntityType, Environment, Position
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
        # Shared
        self.core_pos: Position | None = None
        self.enemy_core: Position | None = None
        self.sym_resolved: Symmetry | None = None
        self.sym_candidates: dict[Symmetry, Position] | None = None
        self.sym_eliminated: set[Symmetry] = set()
        self.known_env: dict[Position, Environment] = {}

        # Core
        self.spawned = 0
        self.base_builders_spawned: int = 0
        self.core_phase = PHASE_SCOUTING
        self.no_report_rounds = 0
        self.launch_wait: int = 0
        self.launch_bot_id: int | None = None
        self.next_spawn_economy: bool = False  # alternates advance/economy spawns
        self.known_splitters: dict | None = (
            None  # {bid: Position} of splitters near core
        )
        self.splitter_resource_counts: dict = {}  # {bid: {ResourceType: int}} observed resource counts
        self.splitter_respawn_queue: list = []  # directions to spawn replacement builders
        self.busiest_spawned_dirs: dict = {}  # direction -> count for busiest-splitter spawns
        self.last_hp: int | None = None  # track core HP to detect damage
        self.damage_spawns_remaining: int = 0  # emergency spawns queued from damage
        self.max_hp_turns: int = 0  # consecutive turns at max HP

        self.spawned_economy: int = 0
        self.spawned_advance: int = 0

        # Builder
        self.economy_wandering: int = 0
        self.base_round: int = 0
        self.state: BuilderState | None = None
        self.target: Position | None = None
        self.base_phase: int = 0
        self.base_wait: int = 0
        self.seen_launcher: bool = False
        self.advance_ore: set[Position] = set()  # ore visited during advance mode
        self.advance_targeting_ore: bool = False  # True if currently diverting to ore
        self.state_seen_enemy: bool = False  # True once enemy core is visible
        self.suicide_countdown: int = 0  # increments toward suicide mode
        self.idle_empty_turns: int = (
            0  # consecutive turns with no resource on conveyor/bridge
        )
        self.heal_no_harvester_turns: int = (
            0  # turns since harvester disappeared in heal mode
        )
        self.can_patch: bool = False
        self.state_turns: int = 0  # turns spent in current state
        self.prev_state: BuilderState | None = None

        # Economy
        self.known_ore: set[Position] = set()  # ore tiles seen by this builder
        self.claimed_ore: set[Position] = (
            set()
        )  # ore tiles we've already harvested/skipped
        self.last_dir: Direction | None = (
            None  # last move direction (for wander momentum)
        )
        self.bridge_target: Position | None = None  # where to place next bridge

        # Bug2 pathfinding
        self.pf_agent: AgentState = AgentState(Position(0, 0), Position(0, 0))
        self.pf_stuck: int = 0
        self.pf_prev_pos: Position | None = None
        self.pf_prev_pos2: Position | None = None
        self.pf_prev_pos3: Position | None = None

    def try_resolve(self, _w: int, _h: int, tag: str) -> bool:
        """Resolve symmetry if only one candidate remains."""
        if self.sym_resolved:
            return True
        if self.sym_candidates is None:
            return False
        remaining = [s for s in SYM_TYPES if s not in self.sym_eliminated]
        resolved_sym: Symmetry | None = None
        resolved_pos: Position | None = None
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
