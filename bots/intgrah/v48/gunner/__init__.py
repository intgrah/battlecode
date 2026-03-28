from cambc import Controller, EntityType
from unit import Unit


class Gunner(Unit):
    def __init__(self, ct: Controller) -> None:
        pass

    def run(self, ct: Controller) -> None:
        my_team = ct.get_team()

        best_target = None
        best_priority = -1

        for bid in ct.get_nearby_buildings():
            if ct.get_team(bid) == my_team:
                continue
            bp = ct.get_position(bid)
            if not ct.can_fire(bp):
                continue
            priority = _target_priority(ct.get_entity_type(bid))
            if priority > best_priority:
                best_priority = priority
                best_target = bp

        for uid in ct.get_nearby_units():
            if ct.get_team(uid) == my_team:
                continue
            up = ct.get_position(uid)
            if not ct.can_fire(up):
                continue
            priority = _target_priority(ct.get_entity_type(uid))
            if priority > best_priority:
                best_priority = priority
                best_target = up

        if best_target is not None:
            ct.fire(best_target)


def _target_priority(etype: EntityType) -> int:
    match etype:
        case EntityType.CORE:
            return 10
        case EntityType.BUILDER_BOT:
            return 5
        case EntityType.HARVESTER:
            return 4
        case EntityType.SPLITTER:
            return 3
        case EntityType.BRIDGE:
            return 2
        case EntityType.CONVEYOR:
            return 1
        case _:
            return 0
