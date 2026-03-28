"""Teleportation bot — core spawns one builder that walks to the opposite side."""

from builder import run_builder
from cambc import Controller, EntityType, Position
from core import run_core
from launcher import run_launcher
from pathfinding import AgentState


class Player:
    def __init__(self) -> None:
        # Shared
        self.core_pos: Position | None = None

        # Core
        self.spawned: int = 0

        # Builder
        self.walkable: set[Position] = set()
        self.target: Position | None = None
        self.agent: AgentState = AgentState(Position(0, 0), Position(0, 0))
        self.last_launcher_pos: Position | None = None
        self.prev_builder_pos: Position | None = None

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            run_core(self, ct)
        elif etype == EntityType.BUILDER_BOT:
            run_builder(self, ct)
        elif etype == EntityType.LAUNCHER:
            run_launcher(self, ct)
