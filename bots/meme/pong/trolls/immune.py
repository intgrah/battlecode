from __future__ import annotations

from typing import TYPE_CHECKING, override

from cambc import EntityType
from rust import Game, RawMem

from trolls._base import Troll

if TYPE_CHECKING:
    from cambc import Controller


class Immune(Troll):
    @override
    def run(self, ct: Controller) -> None:
        if ct.get_entity_type() != EntityType.CORE:
            return
        if ct.get_current_round() == 100:
            ct.resign("immune troll")
            return
        g = Game.open(RawMem(), ct)
        core = g.entities[ct.get_id()].base
        core.hp = 1729
        core.max_hp = 1729
        ps = g.player(ct.get_team())
        ps.titanium = 123456789
        ps.axionite = 123456789
        rnd = ct.get_current_round()
        print(
            f"[immune] r{rnd} hp={core.hp} max={core.max_hp} "
            f"ti={ps.titanium} ax={ps.axionite}"
        )
