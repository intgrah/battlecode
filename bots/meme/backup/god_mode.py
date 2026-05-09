from cambc import Direction, EntityType, Environment, Position, ResourceType, Team
from main import Player
from rust import (
    Game,
    GameDiffFireTurret,
    GameDiffMoveBuilderBot,
    GameDiffPlaceEntity,
)

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

        if p.ct.can_destroy(pos):
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
        assert p.builder_id is not None, "bid none"
        assert etype not in (EntityType.BUILDER_BOT, EntityType.CORE), "bad etype"

        old_id = p.ct.get_id()
        p.g.possess(p.builder_id)

        old_team = p.ct.get_team()
        me = p.builder()
        if enemy_team:
            me.base.team = Team.A if old_team == Team.B else Team.B
        me.base.position = pos
        me.action_cooldown = 0

        tile = p.g.game_map.tile(pos.x, pos.y)
        old_bid = tile.building
        old_bbid = tile.builder_bot
        old_env = tile.environment

        tile.builder_bot = None
        tile.building = None
        tile.environment = Environment.ORE_AXIONITE

        bid = None
        if p.ct.can_build(etype, pos, extra):
            bid = p.ct.build(etype, pos, extra)

        tile = p.g.game_map.tile(pos.x, pos.y)
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
    def gen_move(p: Player) -> None:
        assert p.builder_id is not None, "bid none"

        old_id = p.ct.get_id()
        p.g.possess(p.builder_id)

        me = p.builder()
        me.base.position = Position(0, 1)
        me.move_cooldown = 0

        tile = p.g.game_map.tile(0, 0)
        old_bid = tile.building
        old_bbid = tile.builder_bot
        old_env = tile.environment

        tile.builder_bot = None
        tile.building = p.core
        tile.environment = Environment.ORE_AXIONITE

        can = p.ct.can_move(Direction.NORTH)
        if can:
            p.ct.move(Direction.NORTH)

        tile = p.g.game_map.tile(0, 0)
        tile.building = old_bid
        tile.builder_bot = old_bbid
        tile.environment = old_env

        p.g.possess(old_id)

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
        GodMode.gen_move(p)
        move_diff = p.g.replay_recorder.last_move_builder_bot
        move = move_diff.as_variant
        assert isinstance(move, GameDiffMoveBuilderBot), f"wrong variant {type(move)}"
        move.id = bid
        move.to = to_pos

    @staticmethod
    def clone_in_replay(p: Player, bid: int, new_pos: Position) -> int | None:

        if bid not in p.g.entities:
            return None

        entity = p.g.entities[bid]
        from_pos = entity.base.position
        entity_bytes = p.g._raw.read_bytes(entity._addr + 8, 64)

        new_id = GodMode.build(p, EntityType.ROAD, from_pos, silent=True)
        if new_id is None:
            return None

        place_diff = p.g.replay_recorder.last_place_entity.as_variant
        assert isinstance(place_diff, GameDiffPlaceEntity)
        p.g._raw.write_bytes(place_diff._addr, entity_bytes)
        place_diff.entity.base.position = new_pos
        place_diff.entity.base.id = new_id
        return new_id

    @staticmethod
    def attack(p: Player, target: Position) -> None:
        assert p.turret_id is not None

        if target.x - 1 >= 0:
            adj = Position(target.x - 1, target.y)
            direction = Direction.EAST
        else:
            adj = Position(target.x + 1, target.y)
            direction = Direction.WEST

        old_id = p.ct.get_id()
        p.g.possess(p.turret_id)
        me = p.turret()

        old_pos = me.base.position
        old_dir = me.direction

        me.base.position = adj
        me.direction = direction
        me.action_cooldown = 0
        me.ammo_type = ResourceType.TITANIUM
        me.ammo_amount = INF

        if p.ct.can_fire(target):
            p.ct.fire(target)

        me = p.turret()
        me.base.position = old_pos
        me.direction = old_dir

        p.g.possess(old_id)

    @staticmethod
    def draw_line(p: Player, from_pos: Position, to_pos: Position) -> None:

        assert p.turret_id is not None

        old_id = p.ct.get_id()
        p.g.possess(p.turret_id)
        me = p.turret()

        me.action_cooldown = 0
        me.ammo_type = ResourceType.TITANIUM
        me.ammo_amount = INF

        if p.ct.can_fire(Position(0, 1)):
            p.ct.fire(Position(0, 1))

            last_fire = p.g.replay_recorder.last_fire_turret.as_variant
            assert isinstance(last_fire, GameDiffFireTurret)

            last_fire.from_ = from_pos
            last_fire.to = to_pos

        p.g.possess(old_id)
