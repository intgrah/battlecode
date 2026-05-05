from __future__ import annotations

from itertools import pairwise
from random import Random
from typing import TYPE_CHECKING, override

from apsp import extract_path
from cambc import Direction, Environment, Position
from rust import EntityCore, Game, RawMem
from unit import Unit

if TYPE_CHECKING:
    from cambc import Controller
    from map26 import Map26


class Core(Unit):
    def __init__(
        self,
        m: Map26,
        pnb: list[tuple[int, ...]],
        apsp: list[bytearray],
    ) -> None:
        self.map = m
        self.pnb = pnb
        self.apsp = apsp
        self.passable: list[Position] = [
            Position(x, y)
            for y in range(m.height)
            for x in range(m.width)
            if m.tile(x, y) is not Environment.WALL
        ]
        self.rng = Random(0)

    @override
    def post_init(self, ct: Controller) -> None:
        super().post_init(ct)
        self.rng = Random(self.my_id)

    @override
    def run(self, ct: Controller) -> None:
        super().run(ct)
        g = Game.open(RawMem(), ct)
        if ct.get_current_round() == 1:
            for d in (Direction.NORTHWEST, Direction.NORTH, Direction.NORTHEAST):
                ct.spawn_builder(self.my_pos.add(d))
                me = g.entities[self.my_id].as_variant
                assert isinstance(me, EntityCore)
                me.action_cooldown = 0
        a = self.rng.choice(self.passable)
        b = self.rng.choice(self.passable)
        path = extract_path(self.apsp, self.pnb, self.map.width, (a.x, a.y), (b.x, b.y))
        if path:
            for p, q in pairwise(path):
                ct.draw_indicator_line(p, q, 255, 255, 255)
        else:
            ct.draw_indicator_line(a, b, 255, 0, 0)
