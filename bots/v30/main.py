from builder import BuilderAgent
from cambc import Controller, EntityType
from core import CoreBot
from params import TURN_LIMIT
from turret import TurretUnit


class Player:
    def __init__(self) -> None:
        self.core_bot = CoreBot()
        self.builder = BuilderAgent()
        self.turret = TurretUnit()

    def run(self, ct: Controller) -> None:
        if ct.get_current_round() > TURN_LIMIT:
            return
        match ct.get_entity_type():
            case EntityType.CORE:
                self.core_bot.run(ct)
            case EntityType.BUILDER_BOT:
                self.builder.run(ct)
            case EntityType.GUNNER | EntityType.SENTINEL | EntityType.BREACH:
                self.turret.run(ct)
