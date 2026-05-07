from cambc import Direction, EntityType, Environment, Position, ResourceType, Team
from main import Player
from rust import Game, GameDiffFireTurret, GameDiffPlaceEntity

INF = 1_000_000_000


class GodMode:
    @staticmethod
    def destroy(p: Player, bid: int) -> bool:
        assert p.builder_id is not None

        if bid not in p.g.entities:
            return False

        old_id = p.ct.get_id()
        p.g.possess(p.builder_id)

        entity = p.g.entities[bid].base
        pos = entity.position

        me = p.builder()
        old_team = me.base.team
        me.base.position = pos

        tile = p.g.game_map.tile(pos.x, pos.y)
        old_bid = tile.building
        tile.building = bid

        me.base.team = entity.team

        assert p.ct.can_destroy(pos), "should be able to destroy"
        p.ct.destroy(pos)

        if bid != old_bid:
            tile.building = old_bid

        me = p.builder()
        me.base.team = old_team

        p.g.possess(old_id)
        return True

    @staticmethod
    def build(
        p: Player,
        etype: EntityType,
        pos: Position,
        extra: Position | Direction | None = None,
        enemy_team: bool = False,
        silent: bool = False,
    ) -> int | None:
        assert p.builder_id is not None
        assert etype not in (EntityType.BUILDER_BOT, EntityType.CORE)

        old_id = p.ct.get_id()
        p.g.possess(p.builder_id)

        old_team = p.ct.get_team()
        me = p.builder()
        if enemy_team:
            me.base.team = Team.A if old_team == Team.B else Team.B
        me.base.position = pos
        me.action_cooldown = 0

        assert p.ct.get_action_cooldown() == 0

        tile = p.g.game_map.tile(pos.x, pos.y)
        old_bid = tile.building
        old_bbid = tile.builder_bot
        old_env = tile.environment

        tile.builder_bot = None
        tile.building = None
        tile.environment = Environment.ORE_TITANIUM

        if not p.ct.can_build(etype, pos, extra):
            return None

        bid = p.ct.build(etype, pos, extra)

        if silent:
            tile.building = old_bid
        tile.builder_bot = old_bbid
        tile.environment = old_env

        if enemy_team:
            me = p.builder()
            me.base.team = old_team

        p.g.possess(old_id)
        return bid

    @staticmethod
    def hide_last(g: Game, subsitute_bid: int) -> None:
        bid = subsitute_bid
        entity = g.entities[bid]
        from_pos = entity.base.position
        from_tile = g.game_map.tile(from_pos.x, from_pos.y)
        if from_tile.builder_bot == bid:
            from_tile.builder_bot = None
        if from_tile.building == bid:
            from_tile.building = None
        entity_bytes = g._raw.read_bytes(entity._addr + 8, 64)
        diff_variant = g.replay_recorder.last_place_entity.as_variant
        assert isinstance(diff_variant, GameDiffPlaceEntity)
        g._raw.write_bytes(diff_variant._addr, entity_bytes)
        spawn_base = diff_variant.entity.base
        spawn_base.id = bid
        spawn_base.position = g.entities[bid].base.position

    @staticmethod
    def move(p: Player, bid: int, to_pos: Position, in_replay: bool = True) -> None:

        if bid not in p.g.entities:
            return

        if in_replay:
            GodMode.move_in_replay(p, bid, to_pos)

        entity = p.g.entities[bid]
        from_pos = entity.base.position

        p.g.game_map.tile(from_pos.x, from_pos.y).building = None
        p.g.game_map.tile(to_pos.x, to_pos.y).building = bid
        p.g.entities[bid].base.position = to_pos

    @staticmethod
    def move_in_replay(p: Player, bid: int, to_pos: Position) -> None:
        if bid not in p.g.entities:
            return

        entity = p.g.entities[bid]
        from_pos = entity.base.position
        entity_bytes = p.g._raw.read_bytes(entity._addr + 8, 64)

        if not GodMode.build(p, EntityType.ROAD, from_pos, silent=True):
            return

        place_diff = p.g.replay_recorder.last_place_entity.as_variant
        assert isinstance(place_diff, GameDiffPlaceEntity)
        p.g._raw.write_bytes(place_diff._addr, entity_bytes)
        place_diff.entity.base.position = to_pos

    @staticmethod
    def move_last_in_replay(p: Player, to_pos: Position) -> None:

        place_diff = p.g.replay_recorder.last_place_entity.as_variant
        assert isinstance(place_diff, GameDiffPlaceEntity)
        bid = place_diff.entity.base.id

        if bid not in p.g.entities:
            return

        entity = p.g.entities[bid]
        entity_bytes = p.g._raw.read_bytes(entity._addr + 8, 64)

        p.g._raw.write_bytes(place_diff._addr, entity_bytes)
        place_diff.entity.base.position = to_pos

    @staticmethod
    def draw_line(p: Player, from_pos: Position, to_pos: Position) -> None:

        assert p.turret_id is not None

        old_id = p.ct.get_id()
        p.g.possess(p.turret_id)
        me = p.turret()

        me.action_cooldown = 0
        me.ammo_type = ResourceType.TITANIUM
        me.ammo_amount = INF

        assert p.ct.get_action_cooldown() == 0

        if not p.ct.can_fire(Position(0, 1)):
            return

        p.ct.fire(Position(0, 1))

        last_fire = p.g.replay_recorder.last_fire_turret.as_variant
        assert isinstance(last_fire, GameDiffFireTurret)

        last_fire.from_ = from_pos
        last_fire.to = to_pos

        old_id = p.ct.get_id()
        p.g.possess(old_id)
