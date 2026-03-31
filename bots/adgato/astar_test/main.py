"""A* test bot — core spawns one builder that walks to the opposite corner."""

from typing import TYPE_CHECKING

from builder import run_builder
from cambc import Controller, EntityType, Position
from core import run_core

if TYPE_CHECKING:
    from astar import NavAstar


class Player:
    def __init__(self) -> None:
        # Shared
        self.core_pos: Position | None = None

        # Core
        self.spawned: int = 0

        # Builder
        self.target: Position | None = None
        self.nav: NavAstar | None = None

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            run_core(self, ct)
        elif etype == EntityType.BUILDER_BOT:
            run_builder(self, ct)
