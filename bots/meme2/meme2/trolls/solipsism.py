from __future__ import annotations

from typing import TYPE_CHECKING, override

from cambc import EntityType, Team
from cheats import lie_core_teams, swap_cores
from rust import Game, RawMem

from trolls._base import Troll

if TYPE_CHECKING:
    from cambc import Controller


class Solipsism(Troll):
    def __init__(self) -> None:
        self.patched = False
        self.our_core_id: int | None = None
        self.enemy_core_id: int | None = None

    @override
    def run(self, ct: Controller) -> None:
        if ct.get_entity_type() != EntityType.CORE:
            return
        my_team = ct.get_team()
        enemy_team = Team.A if my_team == Team.B else Team.B
        rnd = ct.get_current_round()

        if not self.patched:
            g = Game.open(RawMem(), ct)
            for bid, e in g.entities.items():
                if e.entity_type != EntityType.CORE:
                    continue
                if e.base.team == my_team:
                    self.our_core_id = bid
                else:
                    self.enemy_core_id = bid
            assert self.our_core_id is not None
            assert self.enemy_core_id is not None

            o_before = g.entities[self.our_core_id].base.position
            e_before = g.entities[self.enemy_core_id].base.position
            print(f"[solip] r{rnd} my_team={my_team} enemy_team={enemy_team}")
            print(
                f"[solip] r{rnd} pre-swap our=({o_before.x},{o_before.y}) enemy=({e_before.x},{e_before.y})"
            )

            swap_cores(g, my_team)

            o_after = g.entities[self.our_core_id].base.position
            e_after = g.entities[self.enemy_core_id].base.position
            print(
                f"[solip] r{rnd} post-swap our=({o_after.x},{o_after.y}) enemy=({e_after.x},{e_after.y})"
            )

            lie_core_teams(
                RawMem(), my_team, enemy_team, self.our_core_id, self.enemy_core_id
            )
            print(
                f"[solip] r{rnd} post-lie ct.get_team(our)={ct.get_team(self.our_core_id)} "
                f"ct.get_team(enemy)={ct.get_team(self.enemy_core_id)}"
            )
            self.patched = True
            return

        if rnd in (10, 100, 1000, 1900):
            print(
                f"[solip] r{rnd} self={ct.get_team()} "
                f"our={ct.get_team(self.our_core_id)} "
                f"enemy={ct.get_team(self.enemy_core_id)}"
            )
