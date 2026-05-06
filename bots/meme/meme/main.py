from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import EntityType, Position
from rust import Game, RawMem
from god_mode import GodMode

INF = 1_000_000_000

if TYPE_CHECKING:
    from cambc import Controller, Team

class Player:
    def __init__(self) -> None:
        self.core: int | None = None
        self.builder: int | None = None
        self.team: Team | None = None
        self.built = False

    def run(self, ct: Controller) -> None:

        if ct.get_entity_type() != EntityType.CORE:
            print("non core got a turn")
            return
        
        try:
            if self.team is None:
                self.team = ct.get_team()

            if self.core is None:
                self.core = ct.get_id()

            if self.builder is None:
                assert ct.can_spawn(ct.get_position())
                self.builder = ct.spawn_builder(ct.get_position())

            g = Game.open(RawMem(), ct)
            g.player(ct.get_team()).titanium = INF

            if not self.built:
                GodMode.spawn(self, g, ct, EntityType.ROAD, Position(10, 10))
                self.built = True

            for i in range(len(g.unit_order)):
                unit_id = g.unit_order[i]
                if unit_id in g.entities and g.entities[unit_id].base.team == self.team:
                    g.unit_order[i] = self.core

        except Exception as e:
            print(e)