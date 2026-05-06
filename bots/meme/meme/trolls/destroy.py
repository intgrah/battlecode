"""Destroy any building (friendly or enemy) anywhere on the map.

Borrows a friendly builder bot — possesses it, teleports it to `pos`,
matches its team to the building's team so the engine accepts the destroy
call, restores everything, releases possession.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rust import EntityBuilderBot, Game

if TYPE_CHECKING:
    from cambc import Controller, Position


def destroy_anywhere(g: Game, ct: Controller, builder_id: int, pos: Position) -> bool:
    """Destroy whatever building stands on `pos`. Returns False if nothing
    to destroy. Builder identity is preserved."""
    old_id = ct.get_id()
    g.possess(builder_id)

    me = g.entities[builder_id].as_variant
    assert isinstance(me, EntityBuilderBot)
    old_team = me.base.team
    me.base.position = pos

    bid = ct.get_tile_building_id(pos)
    if bid is None:
        g.possess(old_id)
        return False

    me.base.team = ct.get_team(bid)
    ct.destroy(pos)

    me = g.entities[builder_id].as_variant
    assert isinstance(me, EntityBuilderBot)
    me.base.team = old_team
    g.possess(old_id)
    return True
