from __future__ import annotations

from typing import TYPE_CHECKING, override

from cambc import EntityType, Team
from rust import Game, RawMem

from trolls._base import Troll

if TYPE_CHECKING:
    from cambc import Controller


class InstantResign(Troll):
    @override
    def run(self, ct: Controller) -> None:
        if ct.get_entity_type() != EntityType.CORE:
            return
        g = Game.open(RawMem(), ct)
        match ct.get_team():
            case Team.A:
                en_team = Team.B
            case Team.B:
                en_team = Team.A

        for bid, entity in g.entities.items():
            if entity.entity_type == EntityType.CORE and entity.base.team == en_team:
                g.possess(bid)
                ct.resign("instant troll")
                return
