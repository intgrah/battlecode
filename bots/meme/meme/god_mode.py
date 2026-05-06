from typing import TYPE_CHECKING

from cambc import Environment, EntityType, Team
from rust import EntityBuilderBot, GameDiffPlaceEntity, GameDiffRemoveEntity

if TYPE_CHECKING:
    from cambc import Position, Controller, Direction
    from main import Player
    from rust import Game

class GodMode:

    @staticmethod
    def destroy(p: Player, g: Game, ct: Controller, pos: Position) -> bool:
        assert p.builder_id is not None
        
        old_id = ct.get_id()
        g.possess(p.builder_id)

        old_team = ct.get_team()
        me = p.builder(g)
        me.base.position = pos
        
        bid = ct.get_tile_building_id(pos)
        if bid is None:
            return False
        
        me.base.team = ct.get_team(bid)

        assert ct.can_destroy(pos), "should be able to destroy"
        ct.destroy(pos)
        
        me = p.builder(g)
        me.base.team = old_team

        g.possess(old_id)
        return True


    @staticmethod
    def build(
        p: Player, 
        g: Game, 
        ct: Controller, 
        etype: EntityType, 
        pos: Position, 
        extra: Position | Direction | None = None, 
        enemy_team: bool = False
    ) -> int | None:
        assert p.builder_id is not None
        assert etype != EntityType.BUILDER_BOT and etype != EntityType.CORE
        
        old_id = ct.get_id()
        g.possess(p.builder_id)
        
        old_team = ct.get_team()
        me = p.builder(g)
        if enemy_team:
            me.base.team = Team.A if old_team == Team.B else Team.B
        me.base.position = pos
        me.action_cooldown = 0

        assert ct.get_action_cooldown() == 0

        tile = g.game_map.tile(pos.x, pos.y)
        old_bbid = tile.builder_bot
        old_env = tile.environment

        tile.builder_bot = None
        tile.building = None
        tile.environment = Environment.ORE_TITANIUM
        
        if not ct.can_build(etype, pos, extra):
            return None
        
        bid = ct.build(etype, pos, extra)

        tile.builder_bot = old_bbid
        tile.environment = old_env

        if enemy_team:
            me = p.builder(g)
            me.base.team = old_team

        g.possess(old_id)
        return bid
    
    @staticmethod
    def place_marker(
        p: Player, 
        g: Game, 
        ct: Controller, 
        pos: Position, 
        enemy_team: bool = False
    ) -> bool:
        assert p.builder_id is not None
        
        old_id = ct.get_id()
        g.possess(p.builder_id)
        
        old_team = ct.get_team()
        me = p.builder(g)
        if enemy_team:
            me.base.team = Team.A if old_team == Team.B else Team.B
        me.base.position = pos
        me.action_cooldown = 0

        assert ct.get_action_cooldown() == 0

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
            me = p.builder(g)
            me.base.team = old_team

        g.possess(old_id)
        return True
    
    @staticmethod
    def move(p: Player, g: Game, ct: Controller, from_pos: Position, to_pos: Position, in_replay: bool = True):

        from_tile = g.game_map.tile(from_pos.x, from_pos.y)
        bid = from_tile.building
        if bid is None or from_pos == to_pos or bid not in g.entities:
            return

        # Snapshot the moving entity's bytes so we can stamp them over the
        # PlaceEntity diff below (skip the bucket's key(4)+pad(4)).
        entity_bytes = g._raw.read_bytes(g.entities[bid]._addr + 8, 64)

        from_tile.building = None
        to_tile = g.game_map.tile(to_pos.x, to_pos.y)

        if in_replay:
            # 1) Build a throwaway road at to_pos to produce a PlaceEntity diff.
            # 2) Repurpose the two diffs:
            #    PlaceEntity{road @ to_pos} → PlaceEntity{bid's entity @ to_pos}
            #    RemoveEntity{road_id}      → RemoveEntity{bid}
            if not GodMode.place_marker(p, g, ct, to_pos):
                return

            place_diff = g.replay_recorder.last_diff.as_variant
            assert isinstance(place_diff, GameDiffPlaceEntity)
            g._raw.write_bytes(place_diff._addr, entity_bytes)
            place_diff.entity.base.position = to_pos

        to_tile.building = bid
        g.entities[bid].base.position = to_pos
