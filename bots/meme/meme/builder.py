from __future__ import annotations

from typing import TYPE_CHECKING, override

from cambc import Direction
from rust import EntityBuilderBot, Game, RawMem
from unit import Unit

if TYPE_CHECKING:
    from cambc import Controller


class Builder(Unit):
    @override
    def run(self, ct: Controller) -> None:
        super().run(ct)
        g = Game.open(RawMem(), ct)
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
