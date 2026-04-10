"""Gunner turret logic — fire at any valid target each round."""

from __future__ import annotations

from cambc import Controller
from unit import Unit


class Gunner(Unit):
    def __init__(self, ct: Controller) -> None:
        pass

    def run(self, ct: Controller) -> None:
        if ct.get_action_cooldown() > 0:
            return
        for tile in ct.get_attackable_tiles():
            if ct.can_fire(tile):
                ct.fire(tile)
                return
