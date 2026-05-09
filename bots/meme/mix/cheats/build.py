"""Build any non-Builder/Core entity anywhere, on any team.

Borrows a friendly builder, possesses it, teleports it to `pos`, optionally
swaps its team to the enemy's, scrubs the target tile (clears any existing
building/bot, paints the environment as titanium ore so harvesters are
allowed) and runs `ct.build`. Restores tile state and team after.

`silent=True` additionally restores the tile's pre-build `building` pointer,
so the new entity exists in `g.entities` but is invisible to the engine's
tile lookup — useful for spawning phantom entities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import EntityType, Environment, Team
from rust import EntityBuilderBot, Game

if TYPE_CHECKING:
    from cambc import Controller, Direction, Position


def build_anywhere(
    g: Game,
    ct: Controller,
    builder_id: int,
    etype: EntityType,
    pos: Position,
    extra: Position | Direction | None = None,
    *,
    enemy_team: bool = False,
    silent: bool = False,
) -> int | None:
    """Build `etype` at `pos`. Returns the new entity id, or None if the
    engine still rejected the build."""
    assert etype != EntityType.BUILDER_BOT
    assert etype != EntityType.CORE

    old_id = ct.get_id()
    g.possess(builder_id)

    me = g.entities[builder_id].as_variant
    assert isinstance(me, EntityBuilderBot)
    old_team = me.base.team
    if enemy_team:
        me.base.team = Team.A if old_team == Team.B else Team.B
    me.base.position = pos
    me.action_cooldown = 0

    tile = g.game_map.tile(pos.x, pos.y)
    old_bid = tile.building
    old_bbid = tile.builder_bot
    old_env = tile.environment
    tile.builder_bot = None
    tile.building = None
    tile.environment = Environment.ORE_TITANIUM

    if not ct.can_build(etype, pos, extra):
        return None

    bid = ct.build(etype, pos, extra)

    if silent:
        tile.building = old_bid
    tile.builder_bot = old_bbid
    tile.environment = old_env

    if enemy_team:
        me = g.entities[builder_id].as_variant
        assert isinstance(me, EntityBuilderBot)
        me.base.team = old_team

    g.possess(old_id)
    return bid
