from builder import BuilderAgent
from cambc import (
    Controller,
    EntityType,
)
from core import CoreBot
from turret import TurretUnit


class Player:
    def __init__(self) -> None:
        self.core_bot = CoreBot()
        self.builder = BuilderAgent()
        self.turret = TurretUnit()

    def run(self, ct: Controller) -> None:
        match ct.get_entity_type():
            case EntityType.CORE:
                self.core_bot.run(ct)
            case EntityType.BUILDER_BOT:
                self.builder.run(ct)
            case EntityType.GUNNER | EntityType.SENTINEL | EntityType.BREACH:
                self.turret.run(ct)
