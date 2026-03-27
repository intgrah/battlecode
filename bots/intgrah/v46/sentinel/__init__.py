from cambc import Controller, EntityType, GameConstants
from entity import Entity


class Sentinel(Entity):
    def __init__(self, ct: Controller) -> None:
        pass

    def run(self, ct: Controller) -> None:
        pos = ct.get_position()
        my_team = ct.get_team()
        best_target = None
        best_priority = -1

        for bid in ct.get_nearby_buildings():
            if ct.get_team(bid) == my_team:
                continue
            bp = ct.get_position(bid)
            if not ct.can_fire(bp):
                continue
            etype = ct.get_entity_type(bid)
            priority = _target_priority(etype)
            if priority > best_priority:
                best_priority = priority
                best_target = bp

        for uid in ct.get_nearby_units():
            if ct.get_team(uid) == my_team:
                continue
            up = ct.get_position(uid)
            if not ct.can_fire(up):
                continue
            etype = ct.get_entity_type(uid)
            priority = _target_priority(etype)
            if priority > best_priority:
                best_priority = priority
                best_target = up

        if best_target is not None:
            ct.fire(best_target)


def _target_priority(etype: EntityType) -> int:
    match etype:
        case EntityType.HARVESTER:
            return 3
        case EntityType.BUILDER_BOT:
            return 2
        case EntityType.CONVEYOR | EntityType.SPLITTER | EntityType.BRIDGE:
            return 1
        case _:
            return 0
