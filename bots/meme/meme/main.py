from __future__ import annotations

import random
from typing import TYPE_CHECKING

from cambc import EntityType, Position
from rust import EntityBuilderBot, Game, RawMem
from trolls import teleport

INF = 1_000_000_000

if TYPE_CHECKING:
    from cambc import Controller, Team


class Player:
    def __init__(self) -> None:
        self.core: int | None = None
        self.builder_id: int | None = None
        self.team: Team | None = None
        self.built = False

    def builder(self, g: Game) -> EntityBuilderBot:
        assert self.builder_id is not None
        me = g.entities[self.builder_id].as_variant
        assert isinstance(me, EntityBuilderBot)
        return me

    def run_troll0(self, ct: Controller) -> None:
        pass

    def run(self, ct: Controller) -> None:
        match random.randint(0, 17):
            case 0:
                self.run_troll0(ct)
            case 1:
                self.run_troll0(ct)

        if ct.get_entity_type() != EntityType.CORE:
            print("non core got a turn")
            return

        try:
            if self.team is None:
                self.team = ct.get_team()

            if self.core is None:
                self.core = ct.get_id()

            if self.builder_id is None:
                assert ct.can_spawn(ct.get_position())
                self.builder_id = ct.spawn_builder(ct.get_position())

            g = Game.open(RawMem(), ct)
            g.player(ct.get_team()).titanium = INF

            if not self.built:
                teleport(g, ct, self.builder_id, ct.get_position(), Position(1, 1))
                self.built = True

            for i in range(len(g.unit_order)):
                unit_id = g.unit_order[i]
                if unit_id in g.entities and g.entities[unit_id].base.team == self.team:
                    g.unit_order[i] = self.core

        except Exception as e:
            print(e)
