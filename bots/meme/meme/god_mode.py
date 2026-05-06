from typing import TYPE_CHECKING

from cambc import Environment, EntityType
from rust import EntityBuilderBot, GameDiffPlaceEntity

if TYPE_CHECKING:
    from cambc import Position, Controller, Direction
    from main import Player
    from rust import Game

class GodMode:

    @staticmethod
    def spawn(p: Player, g: Game, ct: Controller, etype: EntityType, pos: Position, extra: Position | Direction | None = None):

        if p.core is None or p.builder is None:
            return
        
        assert etype != EntityType.BUILDER_BOT and etype != EntityType.CORE
        
        old_id = ct.get_id()
        g.possess(p.builder)

        me = g.entities[p.builder].as_variant
        assert isinstance(me, EntityBuilderBot)
        me.base.position = pos
        me.action_cooldown = 0

        assert ct.get_action_cooldown() == 0

        tile = g.game_map.tile(pos.x, pos.y)
        old_bbid = tile.builder_bot
        old_bid = tile.building
        old_env = tile.environment

        tile.builder_bot = None
        tile.building = None
        tile.environment = Environment.ORE_TITANIUM
        
        if not ct.can_build(etype, pos, extra):
            return
        
        ct.build(etype, pos, extra)

        tile.builder_bot = old_bbid
        tile.building = old_bid
        tile.environment = old_env

        diff = g.replay_recorder.last_diff.as_variant
        assert isinstance(diff, GameDiffPlaceEntity)
        diff.entity.base.position = pos

        g.possess(old_id)