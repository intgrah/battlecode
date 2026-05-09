"""Destroy any entity (friendly or enemy) by id, regardless of tile occupancy.

Borrows a friendly builder bot — possesses it, teleports it onto the
target's tile, matches its team to the target, forces the tile's
`building` pointer to `bid` (so phantom entities not currently on a tile
can still be destroyed), runs `ct.destroy`, then restores everything.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rust import EntityBuilderBot, Game

if TYPE_CHECKING:
    from cambc import Controller


def destroy_anywhere(g: Game, ct: Controller, builder_id: int, bid: int) -> bool:
    """Destroy entity `bid`. Returns False if `bid` no longer exists."""
    if bid not in g.entities:
        return False

    old_id = ct.get_id()
    g.possess(builder_id)

    entity = g.entities[bid].base
    pos = entity.position

    me = g.entities[builder_id].as_variant
    assert isinstance(me, EntityBuilderBot)
    old_team = me.base.team
    me.base.position = pos
    me.base.team = entity.team

    tile = g.game_map.tile(pos.x, pos.y)
    old_bid = tile.building
    tile.building = bid

    assert ct.can_destroy(pos), "should be able to destroy"
    ct.destroy(pos)

    if bid != old_bid:
        tile.building = old_bid

    me = g.entities[builder_id].as_variant
    assert isinstance(me, EntityBuilderBot)
    me.base.team = old_team
    g.possess(old_id)
    return True
