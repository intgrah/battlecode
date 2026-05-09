from __future__ import annotations

from typing import TYPE_CHECKING, override

from cambc import EntityType
from cheats import lie_team
from rust import Game, RawMem

from trolls._base import Troll

if TYPE_CHECKING:
    from cambc import Controller


class Solipsism(Troll):
    @override
    def run(self, ct: Controller) -> None:
        if ct.get_entity_type() != EntityType.CORE:
            return
        g = Game.open(RawMem(), ct)
        lie_team(g, ct.get_team())
