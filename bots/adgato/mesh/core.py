"""Core unit logic — spawn builder bots."""

from __future__ import annotations

from cambc import Controller, Position
from unit import Unit


class Core(Unit):
    def __init__(self, ct: Controller) -> None:
        self.pos = ct.get_position()
        self.spawned = 0

    def run(self, ct: Controller) -> None:
        if self.spawned < 1:
            pos = self.pos
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    p = Position(pos.x + dx, pos.y + dy)
                    if ct.can_spawn(p):
                        ct.spawn_builder(p)
                        self.spawned += 1
                        return
