from __future__ import annotations

from typing import TYPE_CHECKING, override

from cambc import EntityType, Team
from cheats import silence_enemy
from rust import Game, RawMem

from trolls._base import Troll

if TYPE_CHECKING:
    from cambc import Controller


class Silenced(Troll):
    @override
    def run(self, ct: Controller) -> None:
        if ct.get_entity_type() != EntityType.CORE:
            return
        if ct.get_current_round() == 100:
            ct.resign("silenced troll")
            return
        g = Game.open(RawMem(), ct)
        my_team = ct.get_team()
        enemy_team = Team.A if my_team == Team.B else Team.B
        silence_enemy(g, ct.get_id(), enemy_team)

        rnd = ct.get_current_round()
        enemy_count = sum(1 for _, e in g.entities.items() if e.base.team == enemy_team)
        enemy_ti = g.player(enemy_team).titanium
        print(f"[silenced] r{rnd} enemies={enemy_count} enemy_ti={enemy_ti}")
