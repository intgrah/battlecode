"""A* test bot — core spawns builders that walk to random targets."""

from typing import TYPE_CHECKING

from builder import Builder
from cambc import Controller, EntityType
from core import Core
from gunner import Gunner
from launcher import Launcher

if TYPE_CHECKING:
    from unit import Unit


class Player:
    def __init__(self) -> None:
        self.unit: Unit | None = None

    def run(self, ct: Controller) -> None:
        if self.unit is None:
            match ct.get_entity_type():
                case EntityType.CORE:
                    self.unit = Core(ct)
                case EntityType.BUILDER_BOT:
                    self.unit = Builder(ct)
                case EntityType.GUNNER:
                    self.unit = Gunner(ct)
                case EntityType.LAUNCHER:
                    self.unit = Launcher(ct)
                case _:
                    return
        self.unit.run(ct)
