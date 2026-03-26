from typing import TYPE_CHECKING

from builder import Builder
from cambc import Controller, EntityType
from core import Core
from sentinel import Sentinel

if TYPE_CHECKING:
    from entity import Entity


class Player:
    def __init__(self) -> None:
        self.unit: Entity | None = None

    def run(self, ct: Controller) -> None:
        if self.unit is None:
            match ct.get_entity_type():
                case EntityType.CORE:
                    self.unit = Core(ct)
                case EntityType.BUILDER_BOT:
                    self.unit = Builder(ct)
                case EntityType.SENTINEL:
                    self.unit = Sentinel(ct)
                case _:
                    return
        self.unit.run(ct)
