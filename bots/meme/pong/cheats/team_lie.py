"""Make every entity report our team via `get_team`.

Walks `g.entities` and sets each entity's `base.team` field to `our_team`.
The engine's `get_team(id)` reads straight from this field, so subsequent
calls — from our bot or the opponent's — all see our team. Friend/foe
checks in the opponent's logic collapse: their own units look "ours",
ours look "ours", and `ct.get_team()` from any unit returns us.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Team
    from rust import Game


def lie_team(g: Game, our_team: Team) -> None:
    for e in g.entities.values():
        e.base.team = our_team
