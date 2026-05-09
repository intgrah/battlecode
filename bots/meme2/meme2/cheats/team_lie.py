"""Spoof `Controller.get_team` so the two cores' team-queries are swapped.

The engine constructs the `Controller` PyO3 type once in the main
interpreter (`runner.rs:793`) and rebinds it onto each subinterpreter's
`cambc` module via `cambc.setattr("Controller", controller_cls)`. The
type is shared, so a method override here is observed by the opponent's
`ct.get_team()` calls too.

Combined with `swap_cores`, the engine's real state has the two cores
sitting in each other's positions, while every `get_team(core_id)` call
(from either bot) returns the *other* team. Non-core queries pass
straight through.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Controller

from cheats.mutate_type import make_type_mutable, restore_type_flags_invalidate_cache

if TYPE_CHECKING:
    from cambc import Team
    from rust.raw_mem import RawMem


def lie_core_teams(
    raw: RawMem,
    my_team: Team,
    enemy_team: Team,
    our_core_id: int,
    enemy_core_id: int,
) -> None:
    def get_team(self: Controller, id: int | None = None) -> Team:
        actual = id if id is not None else self.get_id()
        if actual == our_core_id:
            return enemy_team
        if actual == enemy_core_id:
            return my_team
        return my_team

    flags = make_type_mutable(Controller, raw)
    Controller.get_team = get_team
    restore_type_flags_invalidate_cache(Controller, raw, flags)
