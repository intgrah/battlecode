"""Sentinel — auto-fires on nearby enemies."""

from cambc import Controller
from unit import Unit


class Sentinel(Unit):
    def run(self, ct: Controller) -> None:
        if ct.get_action_cooldown() != 0:
            return
        my_team = ct.get_team()
        # Fire at highest-priority enemy in range
        for bid in ct.get_nearby_buildings():
            if ct.get_team(bid) != my_team:
                pos = ct.get_position(bid)
                if ct.can_fire(pos):
                    ct.fire(pos)
                    return
        for uid in ct.get_nearby_units():
            if ct.get_team(uid) != my_team:
                pos = ct.get_position(uid)
                if ct.can_fire(pos):
                    ct.fire(pos)
                    return
