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

from cambc import Controller, Direction, EntityType, Environment, Position

from utils import (
    SYM_TYPES, PHASE_SCOUTING,
    get_symmetry_candidates,
)
from pathfinding import AgentState
from core import run_core
from builder import run_builder
from launcher import run_launcher


class Player:
    def __init__(self):
        # Shared
        self.core_pos: Position | None = None
        self.enemy_core: Position | None = None
        self.sym_resolved: str | None = None
        self.sym_candidates: dict[str, Position] | None = None
        self.sym_eliminated: set[str] = set()
        self.known_env: dict[Position, Environment] = {}

        # Core
        self.spawned = 0
        self.core_phase = PHASE_SCOUTING
        self.no_report_rounds = 0

        # Builder
        self.state: str | None = None  # scout_out, scout_report, idle, economy, bridge
        self.target: Position | None = None
        self.candidate_sym: str | None = None
        self.scout_idx: int = -1  # assigned candidate index (0-2)
        self.path: list[Position] = []
        self.visited: set[Position] = set()
        self.comms_written = False
        self.built_launcher = False  # True after building a launcher (wait to be thrown)
        self.last_launcher_pos: Position | None = None

        # Economy
        self.known_ore: set[Position] = set()  # ore tiles seen by this builder
        self.claimed_ore: set[Position] = set()  # ore tiles we've already harvested/skipped
        self.last_dir: Direction | None = None  # last move direction (for wander momentum)
        self.bridge_target: Position | None = None  # where to place next bridge

        # Bug2 pathfinding
        self.pf_agent: AgentState = AgentState(Position(0, 0), Position(0, 0))

    def try_resolve(self, w: int, h: int, tag: str) -> bool:
        """Resolve symmetry if only one candidate remains."""
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
                f"{tag}: resolved [{resolved_sym}] -> "
                f"({resolved_pos.x},{resolved_pos.y})"
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
