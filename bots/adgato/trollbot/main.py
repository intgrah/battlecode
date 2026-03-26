"""Trollbot - clean slate.

Core spawns one builder bot. Builder bot performs symmetry detection
and walks toward unvisited titanium ore deposits.
"""

from builder import run_builder
from cambc import Controller, Direction, EntityType, Environment, Position
from core import run_core
from launcher import run_launcher
from pathfinding import AgentState
from sentinel import run_sentinel


class Player:
    def __init__(self) -> None:
        # Shared
        self.core_pos: Position | None = None
        self.sym_candidates: dict[str, Position] | None = None
        self.sym_eliminated: set[str] = set()
        self.sym_resolved: str | None = None
        self.enemy_core: Position | None = None
        self.known_env: dict[Position, Environment] = {}

        # Core
        self.spawned: int = 0
        self.seen_bridge: bool = False
        self.expansion_cooldown: int = 0
        self.nearest_bridge_id: int | None = None
        self.last_resource_turn: int = 0

        # Builder
        self.walkable: set[Position] = set()
        self.known_ore: set[Position] = set()
        self.claimed_ore: set[Position] = set()
        self.target: Position | None = None
        self.agent: AgentState = AgentState(Position(0, 0), Position(0, 0))
        self.last_dir: Direction | None = None
        self.prev_pos: Position | None = None
        self.wander_target: Position | None = None
        self.secure_target: Position | None = None
        self.mode: str = None  # "advance", "return", "secure", "bridge", "protect"
        self.visited_bridges: set[Position] = set()
        self.bridge_target: Position | None = None
        self.launcher_target: Position | None = None
        self.launcher_failed: Position | None = None
        self.nearest_ore: Position | None = None
        self.small_map: bool = False

    def run(self, ct: Controller) -> None:
        match ct.get_entity_type():
            case EntityType.CORE:
                run_core(self, ct)
            case EntityType.BUILDER_BOT:
                run_builder(self, ct)
            case EntityType.SENTINEL:
                run_sentinel(self, ct)
            case EntityType.LAUNCHER:
                run_launcher(self, ct)
