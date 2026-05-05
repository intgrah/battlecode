from __future__ import annotations

from typing import TYPE_CHECKING

from apsp import apsp, pnb
from builder import Builder
from cambc import EntityType
from core import Core
from map26 import Map26

if TYPE_CHECKING:
    from cambc import Controller
    from unit import Unit


class Player:
    def __init__(self) -> None:
        self.map = m = Map26.read()
        self.pnb = pnb(m)
        self.apsp = apsp(m, self.pnb)
        self.builder = Builder()
        self.core = Core(m, self.pnb, self.apsp)
        self.unit: Unit | None = None

    def run(self, ct: Controller) -> None:
        if self.unit is None:
            match ct.get_entity_type():
                case EntityType.BUILDER_BOT:
                    self.unit = self.builder
                case EntityType.CORE:
                    self.unit = self.core
                case _:
                    return
            self.unit.post_init(ct)
        self.unit.run(ct)
