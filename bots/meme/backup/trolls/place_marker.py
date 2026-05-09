"""Place a marker anywhere, optionally as the enemy team.

Same borrow-builder dance as `build_anywhere` but for markers, which take a
separate code path in the engine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Environment, Team
from rust import EntityBuilderBot, Game

if TYPE_CHECKING:
    from cambc import Controller, Position


def place_marker_anywhere(
    g: Game,
    ct: Controller,
    builder_id: int,
    pos: Position,
    *,
    enemy_team: bool = False,
) -> bool:
    """Place a friendly (or enemy-team) marker at `pos`. Returns False if
    `can_place_marker` rejected the placement."""
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
    old_bbid = tile.builder_bot
    old_env = tile.environment
    tile.builder_bot = None
    tile.building = None
    tile.environment = Environment.ORE_TITANIUM

    if not ct.can_place_marker(pos):
        return False

    ct.place_marker(pos, 0)

    tile.builder_bot = old_bbid
    tile.environment = old_env

    if enemy_team:
        me = g.entities[builder_id].as_variant
        assert isinstance(me, EntityBuilderBot)
        me.base.team = old_team

    g.possess(old_id)
    return True
