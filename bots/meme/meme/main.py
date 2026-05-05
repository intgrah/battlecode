from __future__ import annotations

import astar
from cambc import (
    Controller,
    Direction,
    EntityType,
    Environment,
)
from map26 import Map26
from rust import BuilderBot, Core, Game, RawMem


class Player:
    def __init__(self) -> None:
        self._ti_ore: tuple[int, int] | None = None
        self._ax_ore: tuple[int, int] | None = None
        self._ti_path: list[tuple[int, int]] = []
        try:
            m = Map26.read()
            if m.cores:
                ref_x, ref_y = m.cores[0].x, m.cores[0].y
                best_ti = best_ax = -1
                for y in range(m.height):
                    for x in range(m.width):
                        env = m.tile(x, y)
                        match env:
                            case Environment.ORE_TITANIUM:
                                d = (x - ref_x) ** 2 + (y - ref_y) ** 2
                                if best_ti < 0 or d < best_ti:
                                    best_ti = d
                                    self._ti_ore = (x, y)
                            case Environment.ORE_AXIONITE:
                                d = (x - ref_x) ** 2 + (y - ref_y) ** 2
                                if best_ax < 0 or d < best_ax:
                                    best_ax = d
                                    self._ax_ore = (x, y)
                if self._ti_ore is not None:
                    self._ti_path = astar.run(
                        m, start=self._ti_ore, goal=(ref_x, ref_y)
                    )
        except Exception as e:  # noqa: BLE001
            print(f"[map] {e}")

    def run(self, ct: Controller) -> None:
        self.g = Game.open(RawMem(), ct)
        match ct.get_entity_type():
            case EntityType.CORE:
                self.run_core(ct)
            case EntityType.BUILDER_BOT:
                self.run_builder(ct)

    def run_builder(self, ct: Controller) -> None:
        match ct.get_current_round():
            case 2:
                for i in range(39):
                    print(f"move: {i}")
                    ct.build_road(ct.get_position().add(Direction.NORTH))
                    ct.move(Direction.NORTH)
                    me = self.g.entities[ct.get_id()].as_variant
                    assert isinstance(me, BuilderBot)
                    me.action_cooldown = 0
                    me.move_cooldown = 0

    def run_core(self, ct: Controller) -> None:
        match ct.get_current_round():
            case 1:
                for d in (Direction.NORTHWEST, Direction.NORTH, Direction.NORTHEAST):
                    ct.spawn_builder(ct.get_position().add(d))
                    me = self.g.entities[ct.get_id()].as_variant
                    assert isinstance(me, Core)
                    me.action_cooldown = 0
