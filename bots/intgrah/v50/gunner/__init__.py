from cambc import Controller
from unit import Unit


class Gunner(Unit):
    def __init__(self, ct: Controller) -> None:
        pass

    def run(self, ct: Controller) -> None:
        target = ct.get_gunner_target()
        if target is None or not ct.can_fire(target):
            return
        bid = ct.get_tile_building_id(target)
        if (bid is not None and ct.get_team(bid) == ct.get_team()) or any(
            ct.get_position(uid) == target and ct.get_team(uid) == ct.get_team()
            for uid in ct.get_nearby_units()
        ):
            return
        ct.fire(target)
