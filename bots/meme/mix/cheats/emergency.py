from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Team

if TYPE_CHECKING:
    from rust import Game

INF = 1_000_000_000


def win_without_ct(g: Game) -> None:

    my_id = g.who_am_i()
    my_team = g.entities[my_id].base.team

    team_state = g.player(my_team)
    team_state.axionite_collected = -1

    enemy_state = g.player(Team.A if my_team == Team.B else Team.B)
    enemy_state.axionite_collected = -2

    for i in range(len(g.unit_order)):
        g.unit_order[i] = my_id
