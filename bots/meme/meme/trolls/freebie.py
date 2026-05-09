"""Overwrite a team's stored titanium / refined axionite from thin air.

Mechanism: each team's resources live in `Game.players[team]: PlayerState`,
two consecutive `i32`s. The engine reads them when applying build costs and
writes them back; nothing validates against an external ledger.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Team
    from rust import Game


def freebie(
    g: Game,
    team: Team,
    *,
    titanium: int | None = None,
    axionite: int | None = None,
) -> None:
    """Set `team`'s stored titanium and/or refined axionite. Skips the field
    if its argument is `None`."""
    ps = g.player(team)
    if titanium is not None:
        ps.titanium = titanium
    if axionite is not None:
        ps.axionite = axionite
