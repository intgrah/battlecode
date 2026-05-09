from __future__ import annotations

from typing import TYPE_CHECKING, override

from cambc import Direction, Position
from rust import EntityBuilderBot, EntitySentinel, Game, GameDiffPlaceEntity, RawMem
from unit import Unit

if TYPE_CHECKING:
    from cambc import Controller


class Builder(Unit):
    def road_line(self, ct: Controller, g: Game) -> None:
        if ct.get_current_round() == 2:
            pos = self.my_pos
            for _ in range(39):
                pos = pos.add(Direction.NORTH)
                ct.build_road(pos)
                ct.move(Direction.NORTH)
                me = g.entities[self.my_id].as_variant
                assert isinstance(me, EntityBuilderBot)
                me.action_cooldown = 0
                me.move_cooldown = 0

    def overlay_sentinel(self, ct: Controller, g: Game) -> None:
        if ct.get_current_round() == 2:
            try:
                me = g.entities[self.my_id].as_variant
                assert isinstance(me, EntityBuilderBot)
                original_pos = me.base.position
                g.game_map.tile(original_pos.x, original_pos.y).builder_bot = None
                g.game_map.tile(0, 1).builder_bot = self.my_id
                me.base.position = Position(0, 1)

                dir = Direction.NORTH
                for _i in range(8):
                    if ct.can_build_sentinel(Position(1, 0), dir):
                        sent_id = ct.build_sentinel(Position(1, 0), dir)
                        dir = dir.rotate_right()

                        me = g.entities[self.my_id].as_variant
                        assert isinstance(me, EntityBuilderBot)
                        me.action_cooldown = 0

                        sent = g.entities[sent_id].as_variant
                        assert isinstance(sent, EntitySentinel)
                        g.game_map.tile(1, 0).building = None
                        g.game_map.tile(0, 0).building = sent_id
                        sent.base.position = Position(0, 0)

                        # Keep the replay consistent: rewrite the sentinel's
                        # position inside the just-emitted PlaceEntity diff.
                        diff = g.replay_recorder.last_diff.as_variant
                        assert isinstance(diff, GameDiffPlaceEntity)
                        sent_in_diff = diff.entity.as_variant
                        assert isinstance(sent_in_diff, EntitySentinel)
                        sent_in_diff.base.position = Position(0, 0)
            except Exception as e:
                print(e)

    @override
    def run(self, ct: Controller) -> None:
        super().run(ct)
        g = Game.open(RawMem(), ct)
        self.overlay_sentinel(ct, g)
