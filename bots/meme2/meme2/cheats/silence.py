"""Disable enemy units by hijacking `g.unit_order` entries.

The engine iterates `unit_order` each round and dispatches every entry as
a unit turn (looking the id up in `g.entities` and entering that unit's
subinterpreter). Replacing every enemy id with `my_core_id` resolves
those slots to our core instead — the enemy entities still exist and
keep receiving passive resources, but never get to run their `run(ct)`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Team
    from rust import Game


def silence_enemy(g: Game, my_core_id: int, enemy_team: Team) -> None:
    """Patch every enemy entry in `g.unit_order` to `my_core_id`."""
    for i in range(len(g.unit_order)):
        uid = g.unit_order[i]
        if uid not in g.entities:
            continue
        if g.entities[uid].base.team == enemy_team:
            g.unit_order[i] = my_core_id
