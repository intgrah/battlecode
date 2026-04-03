"""Launcher — throws adjacent enemy bots."""

from cambc import Controller, EntityType
from unit import Unit


class Launcher(Unit):
    def run(self, ct: Controller) -> None:
        if ct.get_action_cooldown() != 0:
            return
        my_team = ct.get_team()
        for uid in ct.get_nearby_units():
            if ct.get_team(uid) != my_team:
                pos = ct.get_position(uid)
                if ct.can_fire(pos):
                    ct.fire(pos)
                    return
